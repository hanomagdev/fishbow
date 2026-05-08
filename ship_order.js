import net from "net";

function sendLegacyXML(xml) {
  return new Promise((resolve, reject) => {
    const client = new net.Socket();
    let response = "";

    const xmlBuffer = Buffer.from(xml, "utf8");
    const lengthBuffer = Buffer.alloc(4);
    lengthBuffer.writeInt32BE(xmlBuffer.length, 0);

    console.log("Connecting to Fishbowl Legacy API...");

    client.connect(28192, "localhost", () => {
      console.log("✔ Connected");

      console.log("Sending length prefix:", lengthBuffer);
      console.log("Sending XML:", xml);

      client.write(lengthBuffer);
      client.write(xmlBuffer);
    });

    client.on("data", data => {
      console.log("📥 Received chunk:", data.toString());
      response += data.toString();
    });

    client.on("end", () => {
      console.log("✔ Connection closed by server");
      resolve(response);
    });

    client.on("error", err => {
      console.log("❌ Socket error:", err);
      reject(err);
    });
  });
}

async function login() {
  const xml = `
  <request>
    <LoginRq>
      <IAID>2286</IAID>
      <IAName>FishbowlAutoShip</IAName>
      <IADescription>Automatic order fulfillment script for pickable orders</IADescription>
      <UserName>ClearviewSolutions</UserName>
      <UserPassword>Clearview7!</UserPassword>
    </LoginRq>
  </request>
  `;

  const res = await sendLegacyXML(xml);
  console.log("LOGIN RESPONSE:", res);
}

login();
