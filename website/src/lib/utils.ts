import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function trackCTAClick(ctaName: string, destination: string) {
  // Send to analytics if available (Google Analytics, etc.)
  if (typeof window !== 'undefined' && (window as any).gtag) {
    (window as any).gtag('event', 'cta_click', {
      event_category: 'conversion',
      event_label: ctaName,
      transport_type: 'beacon',
      event_callback: () => { window.open(destination, '_blank'); }
    });
  }

  // Also log to console in development
  if (import.meta.env.DEV) {
    console.log(`[CTA] ${ctaName} → ${destination}`);
  }
}
