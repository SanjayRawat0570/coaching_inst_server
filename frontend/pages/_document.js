import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" className="dark">
      <Head>
        <meta name="theme-color" content="#070b18" />
        <meta
          name="description"
          content="Smart Coaching — AI agents that teach every JEE/NEET student individually."
        />
      </Head>
      {/* bg color set here too so there is no white flash before CSS loads */}
      <body style={{ backgroundColor: "#070b18", color: "#e2e8f0" }}>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
