import { Html, Head, Main, NextScript } from "next/document";

// Set the theme class before first paint so there is no flash of the wrong theme.
const themeScript = `(function(){try{
  var t = localStorage.getItem('theme');
  if(!t){ t = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'; }
  if(t === 'dark'){ document.documentElement.classList.add('dark'); }
}catch(e){ document.documentElement.classList.add('dark'); }})();`;

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        <meta name="description" content="Smart Coaching — AI agents that teach every JEE/NEET student individually." />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
