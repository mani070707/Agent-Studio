import AuthGuard from "@/components/AuthGuard";
import Nav from "@/components/Nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <Nav>{children}</Nav>
    </AuthGuard>
  );
}
