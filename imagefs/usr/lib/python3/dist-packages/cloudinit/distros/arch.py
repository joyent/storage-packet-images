# Copyright (C) 2014 Rackspace, US Inc.
#
# Author: Nate House <nathan.house@rackspace.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.distros import net_util
from cloudinit.distros.parsers.hostname import HostnameConf

from cloudinit.settings import PER_INSTANCE

import os

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    locale_conf_fn = "/etc/locale.gen"
    network_conf_dir = "/etc/netctl"
    resolve_conf_fn = "/etc/resolv.conf"
    init_cmd = ['systemctl']  # init scripts

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'arch'
        cfg['ssh_svcname'] = 'sshd'

    def apply_locale(self, locale, out_fn=None):
        if not out_fn:
            out_fn = self.locale_conf_fn
        util.subp(['locale-gen', '-G', locale], capture=False)
        # "" provides trailing newline during join
        lines = [
            util.make_header(),
            'LANG="%s"' % (locale),
            "",
        ]
        util.write_file(out_fn, "\n".join(lines))

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('', pkgs=pkglist)

    def _write_network(self, settings):
        entries = net_util.translate_network(settings)
        LOG.debug("Translated ubuntu style network settings %s into %s",
                  settings, entries)
        return _render_network(
            entries, resolv_conf=self.resolve_conf_fn,
            conf_dir=self.network_conf_dir,
            enable_func=self._enable_interface)

    def _enable_interface(self, device_name):
        cmd = ['netctl', 'reenable', device_name]
        try:
            (_out, err) = util.subp(cmd)
            if len(err):
                LOG.warning("Running %s resulted in stderr output: %s",
                            cmd, err)
        except util.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)

    def _bring_up_interface(self, device_name):
        cmd = ['netctl', 'restart', device_name]
        LOG.debug("Attempting to run bring up interface %s using command %s",
                  device_name, cmd)
        try:
            (_out, err) = util.subp(cmd)
            if len(err):
                LOG.warning("Running %s resulted in stderr output: %s",
                            cmd, err)
            return True
        except util.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False

    def _bring_up_interfaces(self, device_names):
        for d in device_names:
            if not self._bring_up_interface(d):
                return False
        return True

    def _write_hostname(self, your_hostname, out_fn):
        conf = None
        try:
            # Try to update the previous one
            # so lets see if we can read it first.
            conf = self._read_hostname_conf(out_fn)
        except IOError:
            pass
        if not conf:
            conf = HostnameConf('')
        conf.set_hostname(your_hostname)
        util.write_file(out_fn, str(conf), omode="w", mode=0o644)

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname_conf(self, filename):
        conf = HostnameConf(util.load_file(filename))
        conf.parse()
        return conf

    def _read_hostname(self, filename, default=None):
        hostname = None
        try:
            conf = self._read_hostname_conf(filename)
            hostname = conf.hostname
        except IOError:
            pass
        if not hostname:
            return default
        return hostname

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ['pacman', "-Sy", "--quiet", "--noconfirm"]
        # Redirect output

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        if command:
            cmd.append(command)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["-y"], freq=PER_INSTANCE)


def _render_network(entries, target="/", conf_dir="etc/netctl",
                    resolv_conf="etc/resolv.conf", enable_func=None):
    """Render the translate_network format into netctl files in target.
    Paths will be rendered under target.
    """

    devs = []
    nameservers = []
    resolv_conf = util.target_path(target, resolv_conf)
    conf_dir = util.target_path(target, conf_dir)

    for (dev, info) in entries.items():
        if dev == 'lo':
            # no configuration should be rendered for 'lo'
            continue
        devs.append(dev)
        net_fn = os.path.join(conf_dir, dev)
        net_cfg = {
            'Connection': 'ethernet',
            'Interface': dev,
            'IP': info.get('bootproto'),
            'Address': "%s/%s" % (info.get('address'),
                                  info.get('netmask')),
            'Gateway': info.get('gateway'),
            'DNS': info.get('dns-nameservers', []),
        }
        util.write_file(net_fn, convert_netctl(net_cfg))
        if enable_func and info.get('auto'):
            enable_func(dev)
        if 'dns-nameservers' in info:
            nameservers.extend(info['dns-nameservers'])

    if nameservers:
        util.write_file(resolv_conf,
                        convert_resolv_conf(nameservers))
    return devs


def convert_netctl(settings):
    """Given a dictionary, returns a string in netctl profile format.

    netctl profile is described at:
    https://git.archlinux.org/netctl.git/tree/docs/netctl.profile.5.txt

    Note that the 'Special Quoting Rules' are not handled here."""
    result = []
    for key in sorted(settings):
        val = settings[key]
        if val is None:
            val = ""
        elif isinstance(val, (tuple, list)):
            val = "(" + ' '.join("'%s'" % v for v in val) + ")"
        result.append("%s=%s\n" % (key, val))
    return ''.join(result)


def convert_resolv_conf(settings):
    """Returns a settings string formatted for resolv.conf."""
    result = ''
    if isinstance(settings, list):
        for ns in settings:
            result = result + 'nameserver %s\n' % ns
    return result

# vi: ts=4 expandtab