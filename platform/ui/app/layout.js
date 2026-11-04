export const metadata = {
  title: "GovAgent platform",
  description: "Policy and evaluate console",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "sans-serif", margin: "2rem", maxWidth: "52rem" }}>{children}</body>
    </html>
  );
}
