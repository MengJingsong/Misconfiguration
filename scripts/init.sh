sudo apt-get update

sudo apt-get -y install vim
sudo apt-get -y install tmux
sudo apt-get -y install htop

SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cp $SCRIPT_DIR/.tmux.conf ~/.tmux.conf

git config --global core.editor "vim"
git config --global user.email "mengjs.92@gmail.com"
git config --global user.name "JingsongMeng"

sudo timedatectl set-timezone America/New_York
