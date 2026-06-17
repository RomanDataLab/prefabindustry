import { Html, Head, Main, NextScript } from 'next/document';
import Script from 'next/script';

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        {/* GTM */}
        <Script
          id="gtm"
          strategy="afterInteractive"
          dangerouslySetInnerHTML={{
            __html: `(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({"gtm.start":
new Date().getTime(),event:"gtm.js"});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!="dataLayer"?"&l="+l:"";j.async=true;j.src=
"https://www.googletagmanager.com/gtm.js?id="+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,"script","dataLayer","GTM-538VHG6H");`,
          }}
        />
        {/* GA4 [RDT-PRFB-48] */}
        <Script
          id="ga4"
          strategy="afterInteractive"
          src="https://www.googletagmanager.com/gtag/js?id=G-2E348VSQ5G"
        />
        <Script
          id="ga4-config"
          strategy="afterInteractive"
          dangerouslySetInnerHTML={{
            __html: `window.dataLayer=window.dataLayer||[];
function gtag(){dataLayer.push(arguments);}
gtag("js",new Date());
gtag("config","G-2E348VSQ5G",{
  custom_map:{"dimension1":"project_name","dimension2":"page_module","dimension3":"user_type","dimension4":"stream_id"},
  project_name:"prefabindustry",
  stream_id:"RDT-PRFB-48",
  page_module:document.title.split("—")[0].trim()||"unknown",
  user_type:(location.search.includes("mode=client")?"client":"ops")
});`,
          }}
        />
      </Head>
      <body>
        <noscript>
          <iframe
            src="https://www.googletagmanager.com/ns.html?id=GTM-538VHG6H"
            height="0"
            width="0"
            style={{ display: 'none', visibility: 'hidden' }}
          />
        </noscript>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
