import type { Metadata } from "next";
import Script from "next/script";
import { Roboto_Slab } from "next/font/google";
import ClientOnly from "./ClientOnly";
import "./globals.css";

const robotoSlab = Roboto_Slab({
  variable: "--font-roboto-slab",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Theia · Agent Dashboard",
  description: "Autonomous paper-trading agent operator dashboard",
};

const STRIP_EXT_ATTRS = `
(function () {
  var re = /^(bis_|__processed_)/;
  function clean(node) {
    if (node && node.attributes) {
      for (var i = node.attributes.length - 1; i >= 0; i--) {
        var n = node.attributes[i].name;
        if (re.test(n)) { try { node.removeAttribute(n); } catch (e) {} }
      }
    }
  }
  function sweep(root) {
    var els = root.querySelectorAll('*');
    for (var i = 0; i < els.length; i++) clean(els[i]);
    clean(root);
  }
  sweep(document.documentElement);
  new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      var m = muts[i];
      if (m.type === 'attributes' && re.test(m.attributeName || '') && m.target) {
        try { m.target.removeAttribute(m.attributeName); } catch (e) {}
      }
    }
  }).observe(document.documentElement, { subtree: true, attributes: true });
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={robotoSlab.variable} suppressHydrationWarning>
      <body suppressHydrationWarning>
        <Script id="strip-ext-attrs" strategy="beforeInteractive">
          {STRIP_EXT_ATTRS}
        </Script>
        <ClientOnly>{children}</ClientOnly>
      </body>
    </html>
  );
}