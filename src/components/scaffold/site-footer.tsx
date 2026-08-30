 import Link from "next/link";
 import { getSectionRoutes } from "@/config/routes";
 
 const footerLinks = [
   ...getSectionRoutes("legal"),
   ...getSectionRoutes("docs"),
 ].map((route) => ({
   href: route.path,
   label: route.title,
 }));
 
 export function SiteFooter() {
   return (
     <footer className="border-t border-[var(--color-line)] bg-[var(--color-surface)]">
       <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
         <div className="flex flex-col gap-2">
           <p className="text-sm font-semibold text-[var(--color-foreground)]">
             Lilly Protocol
           </p>
           <p className="text-xs text-[var(--color-muted)]">
             © {new Date().getFullYear()} Lilly Protocol. All rights reserved.
           </p>
         </div>
         <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-3">
           {footerLinks.map((link) => (
             <Link
               key={link.href}
               href={link.href}
               className="text-sm text-[var(--color-muted)] transition-colors hover:text-[var(--color-foreground)]"
             >
               {link.label}
             </Link>
           ))}
         </nav>
       </div>
     </footer>
   );
 }
