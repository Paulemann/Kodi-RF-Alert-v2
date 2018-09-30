#!/bin/sh

FFMPEGBIN="$(which ffmpeg)"
SNAPSHOTDIR="/home/pi/snapshots"

# onvif1: 1280x720
# onvif2:  320x180
INPUTSTREAM1="rtsp://30.30.30.4:554/onvif2"
INPUTSTREAM2="rtsp://30.30.30.3:554/onvif2"
MAXCAMS=2
TIMEOUT=30

HDINPUTSTREAM1="rtsp://30.30.30.4:554/onvif1"
HDINPUTSTREAM2="rtsp://30.30.30.3:554/onvif1"
HDSNAPSHOTDIR="/home/pi/hd-snapshots"

# check if ffmpeg is running already, else remove existing snapshots and start ffmpeg with rtsp stream input and a predefined timeout after 20 sec
for i in $(seq 1 $MAXCAMS); do
  if [ ! -f "${SNAPSHOTDIR}/${i}"/.dontstart ] ; then
    sudo -u www-data rm "${SNAPSHOTDIR}/${i}"/snapshot* >/dev/null 2>&1
    sudo -u www-data touch "${SNAPSHOTDIR}/${i}"/.dontstart

    CMD="sudo -u www-data ${FFMPEGBIN} -nostdin -rtsp_transport udp -i \${INPUTSTREAM${i}} -an -f image2 -t ${TIMEOUT} -vf fps=fps=5 -vcodec mjpeg \"${SNAPSHOTDIR}/${i}\"/snapshot%03d.jpg >/dev/null 2>&1 ; sudo -u www-data rm \"${SNAPSHOTDIR}/${i}\"/.dontstart"
    eval "${CMD}" &

  fi
done

if [ "$1" = "12345678" ]; then
  i=1
#elif [ "$1" = "" ]; thne
#  i=2
else
  i=0
fi

if [ $i -gt 0 ]; then
  sudo -u www-data rm "${HDSNAPSHOTDIR}"/snapshot* >/dev/null 2>&1
  CMD="sudo -u www-data ${FFMPEGBIN} -nostdin -rtsp_transport udp -i \${HDINPUTSTREAM${i}} -an -f image2 -t 4 -vf fps=fps=3/2 -vcodec mjpeg -strftime 1 \"${HDSNAPSHOTDIR}\"/snapshot_cam${i}_%Y%m%d%H%M%S.jpg >/dev/null 2>&1"
  eval "${CMD}"
fi
