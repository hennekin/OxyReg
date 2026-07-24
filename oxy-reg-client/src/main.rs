use std::io::prelude::*;
use std::net::TcpStream;

fn main() -> std::io::Result<()>{
    let mut stream = TcpStream::connect("127.0.0.1:7000")?;

    let msg_bytes = "Moin mein grosser".as_bytes();
    for mb in msg_bytes {
        stream.write(&[*mb])?;
    }
    // Alternative: stream.write_all(b"Moin mein grosser");

    Ok(())
}
