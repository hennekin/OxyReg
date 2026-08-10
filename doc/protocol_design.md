# Protocol design

- UTF-8 encoded
- send over TCP
- Messages are
  - separated from each other vai a newline "\n"
  - JSON encoded
  - only whitespace character allowed inside JOSN-Objects is space " "
- two way handshake bei register()

## was wollen wir bauen

- register, unregister, list
- Fehelerbenadlung:
  - Doppelte namen bei register()
  - unregister(): was passiert, wenns namen nicht gibt? (silent fail? programmabbruch?)
- Persistenz in memory, als erweiterung sql lite etc?
- Timeout von register()
- Library mit benoetigten typen (zb service name)

## tools

- umwandlung Rust <-> serial: https://serde.rs/

## Extras

- Mutual exclusion ueber tokens als library
