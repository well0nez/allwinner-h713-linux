# The variables of /etc/environment.d/h713-media.conf for login shells (environment.d is read by systemd's user
# manager, not by ssh or the serial console). Same file, so the two cannot disagree.
if [ -r /etc/environment.d/h713-media.conf ]; then
	set -a
	. /etc/environment.d/h713-media.conf
	set +a
fi
