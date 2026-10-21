import "../styles/globals.css";
import Head from "next/head";
import { Inter } from "next/font/google";
import { AuthProvider } from "../lib/useAuth";
import { ToastProvider } from "../components/Toast";
import { ErrorBoundary, OfflineBanner } from "../components/Resilience";

// Self-hosted at build time: no render-blocking request to Google Fonts.
const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });

export default function App({ Component, pageProps }) {
  return (
    <div className={`${inter.variable} ${inter.className}`}>
      <Head>
        <title>Smart Coaching</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <ErrorBoundary>
        <AuthProvider>
          <ToastProvider>
            <OfflineBanner />
            <Component {...pageProps} />
          </ToastProvider>
        </AuthProvider>
      </ErrorBoundary>
    </div>
  );
}
