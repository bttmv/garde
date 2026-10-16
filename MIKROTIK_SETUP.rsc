# نفّذ هذه الأوامر في Terminal الخاص بالراوتر (عدّل أسماء الواجهات والعناوين)
# ملاحظة: ether1 = الإنترنت (WAN) ، bridge-hotspot = شبكة المشتركين

/interface bridge add name=bridge-hotspot
/interface bridge port add bridge=bridge-hotspot interface=wlan1
/ip address add address=10.10.10.1/24 interface=bridge-hotspot
/ip pool add name=hs-pool ranges=10.10.10.10-10.10.10.250
/ip dhcp-server add name=hs-dhcp interface=bridge-hotspot address-pool=hs-pool disabled=no
/ip dhcp-server network add address=10.10.10.0/24 gateway=10.10.10.1 dns-server=8.8.8.8,1.1.1.1
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade

# الهوتسبوت (يمكنك بدلاً من ذلك استخدام: /ip hotspot setup)
/ip hotspot profile add name=hs-prof hotspot-address=10.10.10.1 login-by=http-chap,http-pap
/ip hotspot add name=hotspot1 interface=bridge-hotspot address-pool=hs-pool profile=hs-prof disabled=no

# مستخدم مخصص للبرنامج + تفعيل API (المنفذ 8728)
/user group add name=wifiapp policy=read,write,api,test,policy
/user add name=wifiapp password=ضع_كلمة_مرور_قوية group=wifiapp
/ip service set api disabled=no port=8728 address=192.168.88.0/24
