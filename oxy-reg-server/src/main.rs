use std::io::BufRead;
use std::io::BufReader;
use std::net::TcpListener;
use std::net::TcpStream;

// can be tested by using netcat and sending some text to the socḱet:
// "nc 127.0.0.1 7000"

use serde::{Deserialize, Serialize};
use serde_json::Result;

#[derive(Serialize, Deserialize)]
struct Person {
    name: String,
    age: u8,
    phones: Vec<String>,
}

fn typed_example() -> Result<()> {
    // Some JSON input data as a &str. Maybe this comes from the user.
    let data = r#"
        {
            "name": "John Doe",
            "age": 43,
            "phones": [
                "+44 1234567",
                "+44 2345678"
            ]
        }"#;

    // Parse the string of data into a Person object. This is exactly the
    // same function as the one that produced serde_json::Value above, but
    // now we are asking it for a Person as output.
    let p: Person = serde_json::from_str(data)?;

    // Do things just like with any other Rust data structure.
    println!("Please call {} at the number {}", p.name, p.phones[0]);

    Ok(())
}

fn handle_client(stream: TcpStream) {
    let buf = BufReader::new(stream);
    for line in buf.lines() {
        match line {
            Ok(line) => println!("Empfangen: {}", line),
            Err(e) => {
                // will return an error if the read bytes are not valid UTF-8
                eprintln!("Fehler beim Lesen: {}", e);
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
