from os.path import expanduser
from unittest import TestCase

from paramiko.py3compat import StringIO

from paramiko import SSHConfig
from paramiko.util import lookup_ssh_host_config, parse_ssh_config


# Note some lines in this configuration have trailing spaces on purpose
test_config_file = """\
Host *
    User robey
    IdentityFile    =~/.ssh/id_rsa

# comment
Host *.example.com
    \tUser bjork
Port=3333
Host *
"""

dont_strip_whitespace_please = "\t  \t Crazy something dumb  "

test_config_file += dont_strip_whitespace_please
test_config_file += """
Host spoo.example.com
Crazy something else
"""


class ConfigTest(TestCase):
    def test_parse_config(self):
        global test_config_file
        f = StringIO(test_config_file)
        config = parse_ssh_config(f)
        expected = [
            {"host": ["*"], "config": {}},
            {
                "host": ["*"],
                "config": {"identityfile": ["~/.ssh/id_rsa"], "user": "robey"},
            },
            {
                "host": ["*.example.com"],
                "config": {"user": "bjork", "port": "3333"},
            },
            {"host": ["*"], "config": {"crazy": "something dumb"}},
            {
                "host": ["spoo.example.com"],
                "config": {"crazy": "something else"},
            },
        ]
        assert config._config == expected

    def test_host_config(self):
        global test_config_file
        f = StringIO(test_config_file)
        config = parse_ssh_config(f)

        for host, values in {
            "irc.danger.com": {
                "crazy": "something dumb",
                "hostname": "irc.danger.com",
                "user": "robey",
            },
            "irc.example.com": {
                "crazy": "something dumb",
                "hostname": "irc.example.com",
                "user": "robey",
                "port": "3333",
            },
            "spoo.example.com": {
                "crazy": "something dumb",
                "hostname": "spoo.example.com",
                "user": "robey",
                "port": "3333",
            },
        }.items():
            values = dict(
                values,
                hostname=host,
                identityfile=[expanduser("~/.ssh/id_rsa")],
            )
            assert lookup_ssh_host_config(host, config) == values

    def test_host_config_expose_issue_33(self):
        test_config_file = """
Host www13.*
    Port 22

Host *.example.com
    Port 2222

Host *
    Port 3333
    """
        f = StringIO(test_config_file)
        config = parse_ssh_config(f)
        host = "www13.example.com"
        expected = {"hostname": host, "port": "22"}
        assert lookup_ssh_host_config(host, config) == expected

    def test_proxycommand_config_equals_parsing(self):
        """
        ProxyCommand should not split on equals signs within the value.
        """
        conf = """
Host space-delimited
    ProxyCommand foo bar=biz baz

Host equals-delimited
    ProxyCommand=foo bar=biz baz
"""
        f = StringIO(conf)
        config = parse_ssh_config(f)
        for host in ("space-delimited", "equals-delimited"):
            value = lookup_ssh_host_config(host, config)["proxycommand"]
            assert value == "foo bar=biz baz"

    def test_proxycommand_interpolation(self):
        """
        ProxyCommand should perform interpolation on the value
        """
        config = parse_ssh_config(
            StringIO(
                """
Host specific
    Port 37
    ProxyCommand host %h port %p lol

Host portonly
    Port 155

Host *
    Port 25
    ProxyCommand host %h port %p
"""
            )
        )
        for host, val in (
            ("foo.com", "host foo.com port 25"),
            ("specific", "host specific port 37 lol"),
            ("portonly", "host portonly port 155"),
        ):
            assert lookup_ssh_host_config(host, config)["proxycommand"] == val

    def test_proxycommand_tilde_expansion(self):
        """
        Tilde (~) should be expanded inside ProxyCommand
        """
        config = parse_ssh_config(
            StringIO(
                """
Host test
    ProxyCommand    ssh -F ~/.ssh/test_config bastion nc %h %p
"""
            )
        )
        expected = "ssh -F {}/.ssh/test_config bastion nc test 22".format(
            expanduser("~")
        )
        got = lookup_ssh_host_config("test", config)["proxycommand"]
        assert got == expected

    def test_host_config_test_negation(self):
        test_config_file = """
Host www13.* !*.example.com
    Port 22

Host *.example.com !www13.*
    Port 2222

Host www13.*
    Port 8080

Host *
    Port 3333
    """
        f = StringIO(test_config_file)
        config = parse_ssh_config(f)
        host = "www13.example.com"
        expected = {"hostname": host, "port": "8080"}
        assert lookup_ssh_host_config(host, config) == expected

    def test_host_config_test_proxycommand(self):
        test_config_file = """
Host proxy-with-equal-divisor-and-space
ProxyCommand = foo=bar

Host proxy-with-equal-divisor-and-no-space
ProxyCommand=foo=bar

Host proxy-without-equal-divisor
ProxyCommand foo=bar:%h-%p
    """
        for host, values in {
            "proxy-with-equal-divisor-and-space": {
                "hostname": "proxy-with-equal-divisor-and-space",
                "proxycommand": "foo=bar",
            },
            "proxy-with-equal-divisor-and-no-space": {
                "hostname": "proxy-with-equal-divisor-and-no-space",
                "proxycommand": "foo=bar",
            },
            "proxy-without-equal-divisor": {
                "hostname": "proxy-without-equal-divisor",
                "proxycommand": "foo=bar:proxy-without-equal-divisor-22",
            },
        }.items():

            f = StringIO(test_config_file)
            config = parse_ssh_config(f)
            assert lookup_ssh_host_config(host, config) == values

    def test_host_config_test_identityfile(self):
        test_config_file = """

IdentityFile id_dsa0

Host *
IdentityFile id_dsa1

Host dsa2
IdentityFile id_dsa2

Host dsa2*
IdentityFile id_dsa22
    """
        for host, values in {
            "foo": {"hostname": "foo", "identityfile": ["id_dsa0", "id_dsa1"]},
            "dsa2": {
                "hostname": "dsa2",
                "identityfile": ["id_dsa0", "id_dsa1", "id_dsa2", "id_dsa22"],
            },
            "dsa22": {
                "hostname": "dsa22",
                "identityfile": ["id_dsa0", "id_dsa1", "id_dsa22"],
            },
        }.items():

            f = StringIO(test_config_file)
            config = parse_ssh_config(f)
            assert lookup_ssh_host_config(host, config) == values

    def test_config_addressfamily_and_lazy_fqdn(self):
        """
        Ensure the code path honoring non-'all' AddressFamily doesn't asplode
        """
        test_config = """
AddressFamily inet
IdentityFile something_%l_using_fqdn
"""
        config = parse_ssh_config(StringIO(test_config))
        assert config.lookup(
            "meh"
        )  # will die during lookup() if bug regresses

    def test_config_dos_crlf_succeeds(self):
        config_file = StringIO("host abcqwerty\r\nHostName 127.0.0.1\r\n")
        config = SSHConfig()
        config.parse(config_file)
        assert config.lookup("abcqwerty")["hostname"] == "127.0.0.1"

    def test_get_hostnames(self):
        f = StringIO(test_config_file)
        config = parse_ssh_config(f)
        expected = {"*", "*.example.com", "spoo.example.com"}
        assert config.get_hostnames() == expected

    def test_quoted_host_names(self):
        test_config_file = """\
Host "param pam" param "pam"
    Port 1111

Host "param2"
    Port 2222

Host param3 parara
    Port 3333

Host param4 "p a r" "p" "par" para
    Port 4444
"""
        res = {
            "param pam": {"hostname": "param pam", "port": "1111"},
            "param": {"hostname": "param", "port": "1111"},
            "pam": {"hostname": "pam", "port": "1111"},
            "param2": {"hostname": "param2", "port": "2222"},
            "param3": {"hostname": "param3", "port": "3333"},
            "parara": {"hostname": "parara", "port": "3333"},
            "param4": {"hostname": "param4", "port": "4444"},
            "p a r": {"hostname": "p a r", "port": "4444"},
            "p": {"hostname": "p", "port": "4444"},
            "par": {"hostname": "par", "port": "4444"},
            "para": {"hostname": "para", "port": "4444"},
        }
        f = StringIO(test_config_file)
        config = parse_ssh_config(f)
        for host, values in res.items():
            assert lookup_ssh_host_config(host, config) == values

    def test_quoted_params_in_config(self):
        test_config_file = """\
Host "param pam" param "pam"
    IdentityFile id_rsa

Host "param2"
    IdentityFile "test rsa key"

Host param3 parara
    IdentityFile id_rsa
    IdentityFile "test rsa key"
"""
        res = {
            "param pam": {"hostname": "param pam", "identityfile": ["id_rsa"]},
            "param": {"hostname": "param", "identityfile": ["id_rsa"]},
            "pam": {"hostname": "pam", "identityfile": ["id_rsa"]},
            "param2": {"hostname": "param2", "identityfile": ["test rsa key"]},
            "param3": {
                "hostname": "param3",
                "identityfile": ["id_rsa", "test rsa key"],
            },
            "parara": {
                "hostname": "parara",
                "identityfile": ["id_rsa", "test rsa key"],
            },
        }
        f = StringIO(test_config_file)
        config = parse_ssh_config(f)
        for host, values in res.items():
            assert lookup_ssh_host_config(host, config) == values

    def test_quoted_host_in_config(self):
        conf = SSHConfig()
        correct_data = {
            "param": ["param"],
            '"param"': ["param"],
            "param pam": ["param", "pam"],
            '"param" "pam"': ["param", "pam"],
            '"param" pam': ["param", "pam"],
            'param "pam"': ["param", "pam"],
            'param "pam" p': ["param", "pam", "p"],
            '"param" pam "p"': ["param", "pam", "p"],
            '"pa ram"': ["pa ram"],
            '"pa ram" pam': ["pa ram", "pam"],
            'param "p a m"': ["param", "p a m"],
        }
        incorrect_data = ['param"', '"param', 'param "pam', 'param "pam" "p a']
        for host, values in correct_data.items():
            assert conf._get_hosts(host) == values
        for host in incorrect_data:
            self.assertRaises(Exception, conf._get_hosts, host)

    def test_proxycommand_none_issue_418(self):
        test_config_file = """
Host proxycommand-standard-none
    ProxyCommand None

Host proxycommand-with-equals-none
    ProxyCommand=None
    """
        for host, values in {
            "proxycommand-standard-none": {
                "hostname": "proxycommand-standard-none"
            },
            "proxycommand-with-equals-none": {
                "hostname": "proxycommand-with-equals-none"
            },
        }.items():

            f = StringIO(test_config_file)
            config = parse_ssh_config(f)
            self.assertEqual(lookup_ssh_host_config(host, config), values)

    def test_proxycommand_none_masking(self):
        # Re: https://github.com/paramiko/paramiko/issues/670
        source_config = """
Host specific-host
    ProxyCommand none

Host other-host
    ProxyCommand other-proxy

Host *
    ProxyCommand default-proxy
"""
        config = SSHConfig()
        config.parse(StringIO(source_config))
        # When bug is present, the full stripping-out of specific-host's
        # ProxyCommand means it actually appears to pick up the default
        # ProxyCommand value instead, due to cascading. It should (for
        # backwards compatibility reasons in 1.x/2.x) appear completely blank,
        # as if the host had no ProxyCommand whatsoever.
        # Threw another unrelated host in there just for sanity reasons.
        assert "proxycommand" not in config.lookup("specific-host")
        assert config.lookup("other-host")["proxycommand"] == "other-proxy"
        cmd = config.lookup("some-random-host")["proxycommand"]
        assert cmd == "default-proxy"