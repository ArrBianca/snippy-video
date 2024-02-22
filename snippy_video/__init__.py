#! /usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
import argparse
import json
import re
import shlex
import subprocess
from sys import exit

import argcomplete


# FIXME: Only detects PGS. Look up what other picture formats there are and
#   check against all of them.
# TODO: rename this function
def is_picture_subs(filename: str, index: int):
    media_info = subprocess.run(
        ["mediainfo", "--Output=JSON", filename],
        capture_output=True
    ).stdout

    tracks = json.loads(media_info)["media"]["track"]
    subtitle_tracks = [track for track in tracks if track["@type"] == "Text"]

    if index >= len(subtitle_tracks):
        exit("Invalid subtitle track number.")
    return subtitle_tracks[index]["Format"] == "PGS"


def process_cli():
    parser = argparse.ArgumentParser()

    parser.add_argument("input", help="The video file input")
    # I don't know if these guys are inclusive or exclusive ⬇️
    parser.add_argument(
        "start_ts",
        help="Starting timestamp of the clip in the form "
             "[[HH:]MM:]SS[.MLS] or START",
    )
    parser.add_argument(
        "end_ts",
        help="Ending timestamp of the clip in the form "
             "[[HH:]MM:]SS[.MLS] or END",
    )
    parser.add_argument(
        "output",
        help="Output filename. Make it mp4 pls dont be mean.",
    )
    parser.add_argument(
        "-s", "--simulate",
        help="output ffmpeg command and exit",
        action="store_true",
    )
    parser.add_argument(
        "-v", "--verbose",
        help="do not suppress ffmpeg's output",
        action="store_true",
    )

    # Video options
    video_group = parser.add_argument_group("video options")
    video_group.add_argument(
        "--crf",
        help="override video crf (default %(default)s)",
        default="18",
    )
    video_group.add_argument(
        "--preset",
        help="override encoding preset (default %(default)s)",
        choices=["faster", "fast", "medium", "slow", "slower"],
        default="medium",
    )
    video_group.add_argument(
        "--x264",
        help="encode video in the more supported AVC codec instead",
        action="store_true",
    )
    video_group.add_argument(
        "--quick-cut",
        help="streamcopy video track, almost instant and no quality loss but "
             "impercise start and end times in the output file. "
             "(keyframes, you see)",
        action="store_true",
    )

    # Filter options
    filter_group = parser.add_argument_group("filter options")
    filter_group.add_argument(
        "--burn-subs",
        help="burn subtitles into the output file",
        action="store_true",
    )
    filter_group.add_argument(
        "--sub-stream",
        help="override ffmpeg's subtitle stream choice for burning",
        default="0",
        metavar="sID",
    )
    filter_group.add_argument(
        "--resize",
        help="resize the video while transcoding",
    )

    # Audio options
    audio_group = parser.add_argument_group("audio options")
    # Who knows what happens if you use this on a surround sound track.
    audio_group.add_argument(
        "--recode-audio",
        help="reencode audio track as 128kbps AAC",
        action="store_true",
    )
    audio_group.add_argument(
        "--audio-stream",
        help="override ffmpeg's audio stream choice",
        metavar="aID",
    )
    audio_group.add_argument(
        "--normalize-audio",
        help="normalize output file's audio track to EBU R 128 @ -24LUFS",
        action="store_true",
    )

    argcomplete.autocomplete(parser)
    return parser.parse_args()


def go():
    args = process_cli()
    # print(args)

    # what am i doing
    # this hurts to write
    # i haven't coded in years forgive me

    # Begin and seek.
    # We build the shell command out of its arguments and join them at the end.
    prompt = ["ffmpeg"]
    if not args.verbose:
        prompt += "-loglevel", "quiet", "-stats"
    if args.start_ts != "START":
        prompt += "-ss", args.start_ts,
    if args.end_ts != "END":
        prompt += "-to", args.end_ts,

    # Burn subs is an evil option that needs extra arguments inserted in places
    # outside of the video filter section. We need to copy the seeked(?)
    # timestamp forward then seek separately again through the subtitles after
    # loading the video to get them to match up or at least that's what ffmpeg
    # wiki says. I didn't try it and see what would happen otherwise.
    if args.burn_subs:
        prompt += "-copyts",

    prompt += "-i", args.input,

    # ...but we don't need to if the clip starts from the input file's start.
    if args.burn_subs and args.start_ts != "START":
        prompt += "-ss", args.start_ts,

    filter_complex = ["[0:v]copy"]
    if args.burn_subs:
        # Due to `overlay` needing [video][subtitle] argument order, I
        # can't use the implicit connection of the video stream, as [subtitle]
        # specified on its own will link with the first pad, and order matters.
        # I copy the incoming unnamed video to a named link and use it
        # within the section.
        if is_picture_subs(args.input, int(args.sub_stream)):
            filter_complex += "copy[v1]", f"[v1][0:s:{args.sub_stream}]overlay",
        else:
            filter_complex += f"subtitles={re.escape(args.input)}:stream_index={args.sub_stream}",  # noqa: E501
    if args.resize:
        # If burning and resizing, resizing first provides the best quality.
        # However: if the subtitles are using transforms, the resize will mess
        # those up, so this should come after.
        filter_complex += f"scale={args.resize}", "setsar=1:1"
    if len(filter_complex) > 0:
        prompt += "-filter_complex", ",".join(filter_complex)

    # And again!
    audio_filters = []
    if args.normalize_audio:
        # -24 for movies and TV or -16 for music and podcasts.
        audio_filters += "loudnorm=i=-24",
    if len(audio_filters) > 0:
        prompt += "-af", ",".join(audio_filters)

    # If I ever add more formats this can easily be made a match statement.
    if args.quick_cut:  # Some duplication here but...
        prompt += "-c:v copy",
    elif args.x264:
        prompt += (
            "-c:v", "libx264",
            "-crf", args.crf,
            "-preset", args.preset,
            "-tag:v", "avc1",
            "-pix_fmt", "yuv420p",
        )
    else:  # currently implicit x265
        prompt += (
            "-c:v", "libx265",
            "-crf", args.crf,
            "-preset", args.preset,
            "-tag:v", "hvc1",
        )
        # x265 requires additional work to silence its extra output.
        if not args.verbose:
            prompt += "-x265-params", "log-level=quiet",

    # Strip chapter data. At this point it's misaligned anyway.
    prompt += "-map_chapters", "-1",

    # There used to be more audio options here but the issue I created
    # them to solve turned out to be the result of an old bug in ffmpeg
    # that compiling a new version fixed.
    # TODO: Stream selection should be added back tho.
    # if args.audio_stream:
    #     prompt += '-map', f'a:{args.audio_stream}'
    if args.recode_audio:
        # I don't know what happens if you feed in something surround-sound.
        prompt += "-c:a", "aac_at",
    else:
        prompt += "-c:a", "copy",

    # Finally, the output file.
    prompt += args.output,

    if args.simulate:
        print(shlex.join(prompt))
        exit()

    subprocess.run(prompt)


if __name__ == "__main__":
    go()
