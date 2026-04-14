sudo apt-get update

git config --global core.editor "vim"
git config --global user.email "mengjs.92@gmail.com"
git config --global user.name "JingsongMeng"

sudo timedatectl set-timezone America/New_York

ssh-keygen -t ed25519 -C "meng.479@osu.edu" -f ~/.ssh/id_ed25519 -N ""
