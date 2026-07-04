# Security policy

Steer handles credentials (`steer secrets`) and packages skill directories
for upload (`steer package`), so security reports get priority attention.

## Reporting a vulnerability

Email **bharatgeleda@gmail.com** with the details: proof of concept,
affected version, impact. Please do not open a public issue for anything
exploitable. You should hear back within a few days.

## Scope notes

- `steer secrets` stores values in the OS keychain (macOS `security`,
  Linux `secret-tool`) or a `0600` file under `~/.steer/`, never inside a
  skill directory. Anything that causes a secret to land inside a skill
  directory, a zip, a log, or process output is a vulnerability.
- `steer package` / `steer validate --packaging` are expected to refuse
  credential-looking files. Bypasses are vulnerabilities.
- `steer flow`'s `command` verify condition and `steer proc` execute
  commands **defined by the skill author**: running an untrusted skill is
  running untrusted code. That is inherent to the Agent Skills format, not a
  steer vulnerability; steer's job is to not make it worse (no hidden
  command execution beyond what the skill declares).
