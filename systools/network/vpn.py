import logging

from dbus.mainloop.glib import DBusGMainLoop
import dbus
import gobject


NM = 'org.freedesktop.NetworkManager'

logger = logging.getLogger(__name__)


class AutoVPN(object):

    def __init__(self, vpn_name, max_attempts=10, delay=5000,
            on_connect=None, on_disconnect=None):
        '''
        :param vpn_name: VPN connection name
        :param max_attempts: maximum number of VPN reconnection attempts on failure
        :param delay: VPN reconnection delta (ms)
        '''
        self.vpn_name = vpn_name
        self.max_attempts = max_attempts
        self.delay = delay
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.failed_attempts = 0
        self.bus = dbus.SystemBus()
        self.get_network_manager().connect_to_signal('StateChanged', self.onNetworkStateChanged)
        self.activate_vpn()

    def onNetworkStateChanged(self, state):
        if state == 70:
            self.activate_vpn()

    def onVpnStateChanged(self, state, reason):
        if state == 5:  # connected
            self.failed_attempts = 0
            logger.info('"%s" connected', self.vpn_name)
            if self.on_connect:
                self.on_connect()

        elif state in [6, 7]:   # connection failed or unknown
            if self.on_disconnect:
                self.on_disconnect()

            if not self.max_attempts or self.failed_attempts < self.max_attempts:
                logger.error('"%s" disconnected, attempting to reconnect', self.vpn_name)
                self.failed_attempts += 1
                gobject.timeout_add(self.delay, self.activate_vpn)
            else:
                logger.error('"%s" disconnected, exceeded %d max attempts', self.vpn_name, self.max_attempts)
                self.failed_attempts = 0

    def get_network_manager(self):
        '''Get the network manager dbus interface.
        '''
        proxy = self.bus.get_object(NM, '/org/freedesktop/NetworkManager')
        return dbus.Interface(proxy, NM)

    def get_vpn_interface(self, name):
        '''Get the VPN connection interface with the specified name.
        '''
        proxy = self.bus.get_object(NM, '/org/freedesktop/NetworkManager/Settings')
        iface = dbus.Interface(proxy, NM + '.Settings')
        for con in iface.ListConnections():
            proxy = self.bus.get_object(NM, con)
            iface = dbus.Interface(proxy, NM + '.Settings.Connection')
            con_settings = iface.GetSettings()['connection']
            if con_settings['type'] == 'vpn' and con_settings['id'] == name:
                return iface
        logger.error('failed to acquire "%s" VPN interface', name)

    def get_active_connection(self):
        '''Get the dbus interface of the first active network connection.
        '''
        proxy = self.bus.get_object(NM, '/org/freedesktop/NetworkManager')
        iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
        active = iface.Get(NM, 'ActiveConnections')
        if active:
            return active[0]
        logger.error('no active connection')

    def bind_interface(self, con):
        proxy = self.bus.get_object(NM, con)
        iface = dbus.Interface(proxy, NM + '.VPN.Connection')
        iface.connect_to_signal('VpnStateChanged', self.onVpnStateChanged)

    def activate_vpn(self):
        vpn_con = self.get_vpn_interface(self.vpn_name)
        if vpn_con is None:
            return
        active_con = self.get_active_connection()
        if active_con is None:
            return

        proxy = self.bus.get_object(NM, active_con)
        iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')

        # Check VPN state
        uuid = vpn_con.GetSettings()['connection']['uuid']
        if iface.Get(NM + '.Connection.Active', 'Uuid') == uuid:
            state = iface.Get(NM + '.VPN.Connection', 'VpnState')
            if state == 5:  # connected
                self.bind_interface(active_con)
                if self.on_connect:
                    self.on_connect()
                return

        # Activate VPN
        new_con = self.get_network_manager().ActivateConnection(vpn_con,
                dbus.ObjectPath('/'), active_con)
        self.bind_interface(new_con)


def watch_vpn(vpn_name, **kwargs):
    DBusGMainLoop(set_as_default=True)
    loop = gobject.MainLoop()
    AutoVPN(vpn_name, **kwargs)
    loop.run()
