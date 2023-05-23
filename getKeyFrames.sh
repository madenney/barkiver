
#
# $1 - input
# $2 - output

ffprobe -loglevel error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=print_section=0 $1 | awk -F',' '/K/ {print $1}' > $2
