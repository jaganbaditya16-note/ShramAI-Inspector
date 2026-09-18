import './globals.css';

export const metadata = { title: 'ShramAI Inspector', description: 'AI-assisted labour compliance inspection' };

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
