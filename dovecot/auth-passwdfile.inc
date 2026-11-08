# Authentication for passwd-file users. Included from 10-auth.conf.
#
# passwd-like file with specified location.
# <doc/wiki/AuthDatabase.PasswdFile.txt>

passdb passwd-file {
  default_password_scheme = CRYPT
  auth_username_format = %{user}
  passwd_file_path = /etc/dovecot/userdb
}

userdb passwd-file {
  auth_username_format = %{user}
  passwd_file_path = /etc/dovecot/userdb
}
