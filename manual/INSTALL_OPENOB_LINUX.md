INSTALAR EN LINUX
python3 -m pip install --user -U pip setuptools wheel
python3 -m pip install --user -U --force-reinstall .
pip install .


wilber
sudo pip3 install .
echo 'export PATH=$PATH:/usr/local/bin' >> ~/.bashrc
sudo pip3 uninstall openob
openob 192.168.1.15 recepteur transmission rx -a alsa -d hw:1,0 -j 3000
