import Navigation from './Navigation';
import ThemeToggle from './theme-toggle';

export default function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container max-w-6xl mx-auto px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex-1 min-w-fit items-center gap-2">
            <h1 className="text-lg font-semibold min-w-fit">VoxBridge</h1>
          </div>
          <Navigation />
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
