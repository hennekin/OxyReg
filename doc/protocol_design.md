# Protocol design

- UTF-8 encoded
- send over TCP
- Messages are
  - separated from each other vai a newline "\n"
  - JSON encoded
  - only whitespace character allowed inside JOSN-Objects is space " "
