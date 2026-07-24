use std::io::BufRead;
use std::io::BufReader;
use std::net::TcpListener;
use std::net::TcpStream;

// can be tested by using netcat and sending some text to the socḱet:
// "nc 127.0.0.1 7000"

fn handle_client(stream: TcpStream) {
    let buf = BufReader::new(stream);
    for line in buf.lines() {
        match line {
            Ok(line) => println!("Empfangen: {}", line),
            Err(e) => {
                eprintln!("Fehler beim Lesen: {}", e);
                break;
            }
        }
    }
}

fn main() {
    let tcp_listener;
    let listener = TcpListener::bind("0.0.0.0:7000");
    match listener {
        Ok(l) => tcp_listener = l,
        Err(e) => {
            eprintln!("{}", e);
            return;
        }
    }

    // accept connections and process them serially
    for stream in tcp_listener.incoming() {
        match stream {
            Ok(stream) => {
                handle_client(stream);
            }
            Err(_e) => {
                println!("Something went wrong")
            }
        }
    }
}
