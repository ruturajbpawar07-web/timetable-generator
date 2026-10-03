"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AlertTriangle, BarChart3, BookOpen, Bot, CalendarDays, CalendarX, DoorOpen, GaugeCircle, History,
  LayoutDashboard, Menu, Moon, Settings, Sparkles, Sun, UserCog, Users, UsersRound,
} from "lucide-react";
import { Toaster, cx } from "./ui";
import { useMeta } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/timetable", label: "Timetable", icon: CalendarDays },
  { href: "/generate", label: "Generate Timetable", icon: Sparkles },
  { href: "/faculty", label: "Faculty", icon: Users },
  { href: "/classes", label: "Classes", icon: UsersRound },
  { href: "/subjects", label: "Subjects", icon: BookOpen },
  { href: "/rooms", label: "Rooms & Labs", icon: DoorOpen },
  { href: "/substitutions", label: "Substitutions", icon: UserCog },
  { href: "/absences", label: "Absences", icon: CalendarX },
  { href: "/conflicts", label: "Conflicts", icon: AlertTriangle },
  { href: "/workload", label: "Workload", icon: GaugeCircle },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/assistant", label: "Smart Assistant", icon: Bot },
  { href: "/audit", label: "Audit Log", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const meta = useMeta();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  useEffect(() => setOpen(false), [path]);
  const toggle = () => {
    const d = !dark;
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
    try { localStorage.theme = d ? "dark" : "light"; } catch {}
  };
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <div className="flex min-h-screen">
      <aside className={cx("fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-slate-200 bg-white transition-transform dark:border-zinc-800 dark:bg-zinc-900 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex h-14 items-center gap-2 border-b border-slate-100 px-4 dark:border-zinc-800">
          <div className="grid size-8 place-items-center rounded-lg bg-indigo-600 text-white"><CalendarDays className="size-4" /></div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">Dream Timetable</div>
            <div className="text-[11px] text-slate-500 dark:text-zinc-400">{meta?.academic_year ?? "…"}</div>
          </div>
        </div>
        <nav className="h-[calc(100vh-3.5rem)] space-y-0.5 overflow-y-auto p-2">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href}
              className={cx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition",
                active(href) ? "bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                  : "text-slate-600 hover:bg-slate-50 dark:text-zinc-400 dark:hover:bg-zinc-800")}>
              <Icon className="size-4" />{label}
            </Link>
          ))}
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/80 lg:px-8">
          <button className="rounded p-1.5 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="size-5" /></button>
          <div className="truncate text-sm font-medium text-slate-600 dark:text-zinc-300">{meta?.college ?? "College"}</div>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-xs text-slate-500 sm:inline">Admin</span>
            <button onClick={toggle} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-zinc-800" aria-label="Toggle dark mode">
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-[1500px] p-4 lg:p-8">{children}</main>
      </div>
      <Toaster />
    </div>
  );
}
