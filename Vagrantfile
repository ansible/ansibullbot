# -*- mode: ruby -*-
# vi: set ft=ruby :

$script = <<SCRIPT
# AUTHENTICATION
echo 'root:vagrant' | chpasswd
echo 'vagrant:vagrant' | chpasswd
egrep "^PasswordAuthentication yes" /etc/ssh/sshd_config
RC=$?
if [[ $RC != 0 ]]; then
    echo "Enabling ssh passwords"
    sed -i.bak 's/PasswordAuthentication\ no/PasswordAuthentication\ yes/' /etc/ssh/sshd_config
    service sshd restart
fi

# BASELINE PACKAGES
PACKAGES="epel-release ansible git rsync vim-enhanced bind-utils policycoreutils-python net-tools lsof"
for PKG in $PACKAGES; do
    rpm -q $PKG || yum -y install $PKG
done

# VIMRC
rm -f /etc/vimrc
cp /vagrant/playbooks/files/centos7.vimrc /etc/vimrc

# WORKAROUNDS
setenforce 0
fgrep docker /etc/group || groupadd -g 993 docker
fgrep ansibot /etc/group || groupadd -g 1099 ansibot
id ansibot || useradd -u 1099 -g ansibot ansibot
usermod -a -G docker ansibot
rsync -avz --exclude='/vagrant/.vagrant' /vagrant/* /home/ansibot/ansibullbot

# PSEUDO ANSIBLE-LOCAL PROVISIONER
setenforce 0
echo "ansibullbot ansible_host=localhost ansible_connection=local" > /tmp/inv.ini
echo "ansibullbot.eng.ansible.com ansible_host=localhost ansible_connection=local" >> /tmp/inv.ini
cd /vagrant/playbooks
#PLAYBOOKS="setup-ansibullbot.yml"
PLAYBOOKS="vagrant.yml"
for PLAYBOOK in $PLAYBOOKS; do
    ansible-playbook \
        -v \
        -i /tmp/inv.ini \
        --skip-tags=ssh \
        $PLAYBOOK
done

#        --tags=packages,ansibullbot,caddy \
#        --skip-tags=botinstance,dns,ssh,ansibullbot_service,ansibullbot_logs \
#--skip-tags=botinstance,dns,ssh,ansibullbot_service,ansibullbot_logs \
#    -e "ansibullbot_action=install" \
# HACK IN FIREWALL EXCEPTIONS
firewall-cmd --zone=public --add-port=80/tcp --permanent
firewall-cmd --reload

SCRIPT


Vagrant.configure("2") do |config|
  config.vm.box = "centos/7"
  config.vm.hostname = "ansibullbot.eng.ansible.com"
  config.hostmanager.enabled = true
  config.hostmanager.manage_host = true
  config.hostmanager.manage_guest = true
  config.hostmanager.ignore_private_ip = false
  config.hostmanager.include_offline = true
  config.vm.network "private_network", ip: "10.0.0.210"
  config.vm.synced_folder ".", "/vagrant", type: "nfs", nfs_udp: false

  config.vm.provider :libvirt do |libvirt|
    libvirt.cpus = 2
    libvirt.memory = 2048
  end

  config.vm.provision "shell", inline: $script
end
