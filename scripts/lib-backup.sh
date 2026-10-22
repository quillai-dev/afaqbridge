# Shared helpers for backup/restore (sourced). Encrypt-then-MAC:
#   <file>      AES-256-CBC (PBKDF2, 600k iterations) of the tar stream
#   <file>.mac  HMAC-SHA256 over <file>, key = SHA256("ao-mac-v1:" || passphrase)  -> detects any modification,
#               including by someone who can rewrite both files but does not know the passphrase.
#   <file>.sha256 plain checksum (accidental corruption / transfer errors only; NOT tamper evidence)
ao_mackey() { { printf 'ao-mac-v1:'; cat "$1"; } | openssl dgst -sha256 -binary | od -An -tx1 | tr -d ' \n'; }
ao_mac()    { openssl dgst -sha256 -mac HMAC -macopt hexkey:"$(ao_mackey "$2")" -r "$1" | cut -d' ' -f1; }
ao_seal()   { # ao_seal <encrypted-file> <passphrase-file>
  ao_mac "$1" "$2" > "$1.mac"; sha256sum "$1" | cut -d' ' -f1 > "$1.sha256"; chmod 600 "$1.mac" "$1.sha256"; }
ao_verify() { # ao_verify <encrypted-file> <passphrase-file>  -> 0 only if the MAC matches
  [ -s "$1.mac" ] || { echo "INTEGRITY FAILURE: $1.mac missing" >&2; return 1; }
  local want got; want=$(cat "$1.mac"); got=$(ao_mac "$1" "$2")
  [ "${#want}" = 64 ] && [ "$want" = "$got" ] || { echo "INTEGRITY FAILURE: MAC mismatch for $1 - file modified/corrupt or wrong passphrase; NOT restoring" >&2; return 1; }; }
