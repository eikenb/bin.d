#!/bin/sh

# Script to split up whole album youtube entries. Just need to save album in
# file name "artist-album.enc-suffix" and then create a file of the songs
# formatted "song title duration-min:dur-sec".

# use "skip min:sec" if there is dead air you want to skip in the file

album="$1"
# format is one song per line, "song name min:sec"
songs="$2"

# newstart pre-start min:sec
# eg. `newstart 10:11 3:05` -- prints `13:16`
newstart() {
    local start="$1"
    local M="${2%%:*}"
    local S="${2##*:}"
    date -d "19700101 00:$start ${M}min${S}sec" +"%M:%S"
}
#newstart 10:11 3:05

start=00:00
count=1
enc=${album##*.}

album_name="$(basename $album .$enc | tr '_' ' ')"
artist="${album_name%-*}"
album_name="${album_name##*-}"

IFS="$(printf '\n\r')"
for songinfo in $(cat $songs)
do
    [ -n "$songinfo" ] || continue
    length="${songinfo##* }"
    title="${songinfo% *}"

    if [ "$title" = "skip" ]; then
        start=$(newstart $start $length)
        echo skipping to $start
        continue
    fi

    filename="$(echo $title | tr 'A-Z' 'a-z' | tr ' ' '_')"
    filename="$(printf '%02i' $count).${filename}.${enc}"

    echo ffmpeg -i "$album" -acodec copy -ss $start -t $length $filename
    ffmpeg -loglevel 0 -i "$album" -acodec copy -ss $start -t $length $filename

    start=$(newstart $start $length)
    count=$(($count + 1))

    lltag --yes -A "$album_name" -a "$artist" -t "$title" -n $count "$filename"
    case $enc in
        ogg) vorbisgain "$filename" ;;
        mp3) replaygain -f "$filename" ;;
        flac) metaflac --add-replay-gain "$filename" ;;
    esac
done
