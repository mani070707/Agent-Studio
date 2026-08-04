import "./globals.css";

export const metadata = {
  title: "Agent Studio",
  description: "Author, test, evaluate, and run tool-calling AI agents.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
