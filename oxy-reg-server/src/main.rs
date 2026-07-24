use std::net::TcpListener;
use std::net::TcpStream;

fn handle_client(_stream: TcpStream) {
    // hier müsste Zeileweise gelesen werden
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
