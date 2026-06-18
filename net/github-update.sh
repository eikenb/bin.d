#!/bin/sh

set -e
umask 002

usage() {
    echo "Set environment variables: ORG, PROJECT, NAME_REGEX, COMMAND"
    echo "Optional: TEST_REGEX (false), INSTALL_DIR ($INSTALL_DIR), NEEDSDIR (false)"
    echo "Usage: $0"
    echo "Example: ORG=golang PROJECT=go NAME_REGEX='go.*linux-amd64.tar.gz' COMMAND=go $0"
    exit 1
}

[ -n "$INSTALL_DIR" ] || INSTALL_DIR=~/.local/bin

if [ -z "$ORG" ] || [ -z "$PROJECT" ] || [ -z "$NAME_REGEX" ] || [ -z "$COMMAND" ]; then
    usage
fi

package=
download() {
  package=$(curl -s "https://api.github.com/repos/$ORG/$PROJECT/releases/latest" \
    | jq -r '.assets[] | select(.name |test("'"$NAME_REGEX"'")) | .name')

  case "$TEST_REGEX" in T*|t*|1|Y*|y*)
    curl -s "https://api.github.com/repos/$ORG/$PROJECT/releases/latest" \
        | jq -r '.assets[] | select(.name |test("'"$NAME_REGEX"'"))' # | hl .browser_download_url
    exit 123
  esac

  curl -s "https://api.github.com/repos/$ORG/$PROJECT/releases/latest" \
      | jq -r '.assets[] | select(.name |test("'"$NAME_REGEX"'")) | .browser_download_url' \
      | wget -q --show-progress -O "$package" -i -
  digest=$(curl -s "https://api.github.com/repos/$ORG/$PROJECT/releases/latest" \
    | jq -r '.assets[] | select(.name |test("'"$NAME_REGEX"'")) | .digest')
  # shellcheck disable=SC2046
  if test "${digest#sha256:}" != $(sha256sum "$package" | awk "{print \$1}") ; then
    echo "SHA mismatch?!?!"
    echo "'$digest' != '$(sha256sum $package)'"
    exit 124
  else
    echo "SHA's match!"
  fi
}

unpack_tar_command() {
  [ -z "$package" ] && { echo "no package"; exit 1 ; }
  strip=$(tar vtf "$package" | \
    awk '/\/'"$COMMAND"'$|^'"$COMMAND"'$/ {saved=$NF}; {count+=gsub(/\//,"",saved)} END {print count}')

  [ -n "$strip" ] || strip=0
  tar vxf "$package" --strip-components="$strip" --no-anchored -C "$INSTALL_DIR" "$COMMAND"
}

unpack_tar_directory() {
  [ -z "$package" ] && { echo "no package"; exit 1 ; }
  topdir_count=$(tar -tf "$package" | sort | awk -F'/' '{print $1}' | uniq | wc -l)
  case $topdir_count in
    0)
      echo "pacakge was empty? .." && tar -tf "$package"
      exit 1
      ;;
    1)
      optarg="--strip-components=1"
    ;;
  esac
  COMMAND_DIR="$INSTALL_DIR/$COMMAND.files"
  mkdir -p "$COMMAND_DIR"
  tar vxf "$package" $optarg -C "$COMMAND_DIR"
  if test -L "$INSTALL_DIR/$COMMAND" && test -x "$INSTALL_DIR/$COMMAND"
  then
    return
  fi
  ( 
    cd "$INSTALL_DIR"
    ln -s "$(find "$COMMAND_DIR" -type f -name "$COMMAND" -executable | head -1)" "$COMMAND"
  )
}

cleanup() {
  [ -n "$package" ] && rm "$package"
}

###

# ~/tmp as working dir
mkdir -p ~/tmp
cd ~/tmp || { echo "Failed to change directory to ~/tmp"; exit 1; }


download

case "$package" in
    *.tar.*|*.tgz)
        if [ -n "$NEEDSDIR" ]; then unpack_tar_directory; else unpack_tar_command; fi
        ;;
    *.deb)
        sudo apt install ./"$package"
        ;;
    *.zip)
        unzip -o "$package" -d $INSTALL_DIR
        ;;
    *.gz)
        gunzip "$package" --stdout > "$INSTALL_DIR/$COMMAND"
        chmod 750 "$INSTALL_DIR/$COMMAND"
        ;;
    *)
        cp -v "$package" "$INSTALL_DIR/$COMMAND"
        chmod 750 "$INSTALL_DIR/$COMMAND"
        ;;
esac

cleanup

