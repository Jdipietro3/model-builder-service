import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ProjectsProvider } from "@/lib/projects-context";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Metis",
  description: "Chat-driven ML model training for engineers",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* The app is a fixed-height two-or-three column shell: the rail and the
          chat scroll independently of the content column, so the page itself
          never scrolls. Each route supplies its own <Sidebar>. */}
      <body className="h-full overflow-hidden bg-zinc-950 text-zinc-100">
        {/* Holds only the project LIST, above every route, so the rail keeps its
            contents when moving between `/` and a project. */}
        <ProjectsProvider>{children}</ProjectsProvider>
      </body>
    </html>
  );
}
