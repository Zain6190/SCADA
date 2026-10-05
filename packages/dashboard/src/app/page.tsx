'use client'

import Link from 'next/link'
import Image from 'next/image'
import { ArrowRight, ArrowUpRight, Waves, Radio, Sprout, ShieldCheck, FileText, MapPin } from 'lucide-react'
import { BrandMark } from '@/components/shared/brand-mark'
import { useAuth } from '@/context/AuthContext'
import { homeFor } from '@/context/AuthContext'
import styles from './landing.module.css'

const WORKFLOW = [
  { title: 'Read the observation', body: 'An IRSA reading or FFD bulletin arrives. The asset, source and observation time stay attached to the record.', tag: 'Official observations', icon: FileText },
  { title: 'Review the alert', body: 'An asset threshold identifies a condition that needs attention. The operator reviews its severity and supporting evidence.', tag: 'Asset thresholds', icon: Waves },
  { title: 'Inspect downstream impact', body: 'Check connected assets and the available impact analysis. Model output remains distinguishable from measured conditions.', tag: 'Downstream analysis', icon: MapPin },
  { title: 'Record the decision', body: 'Acknowledge, investigate or escalate the alert. Role-based permissions and an audit trail keep the action traceable.', tag: 'Operator review', icon: ShieldCheck },
]

export default function LandingPage() {
  const { user, loading } = useAuth()
  const signedIn = !loading && !!user
  const consoleHref = signedIn ? homeFor(user) : '/login'

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark} aria-label="IBCP-SCADA home">
          <span className={styles.brandTile}><BrandMark width={32} height={32} /></span>
          <span><strong>IBCP-SCADA</strong><small>Indus Basin Operations</small></span>
        </Link>
        <nav className={styles.navigation} aria-label="Main navigation">
          <a href="#platform">The platform</a>
          <a href="#workflow">How it works</a>
          <Link href={consoleHref} className={styles.headerAction}>{signedIn ? 'Open workspace' : 'Sign in'}<ArrowUpRight size={15} aria-hidden="true" /></Link>
        </nav>
      </header>

      <main>
        <section className={styles.hero} aria-labelledby="hero-heading">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}><span /> INDUS BASIN / PAKISTAN</p>
            <h1 id="hero-heading">Water operations<br />across the<br /><em>Indus Basin.</em></h1>
            <p className={styles.heroLede}>Monitor reservoirs and barrages, review flood forecasts, and trace operator decisions in one platform.</p>
            <div className={styles.heroActions}>
              <Link href={consoleHref} className={styles.primaryAction}>{signedIn ? 'Open your workspace' : 'Explore the console'}<ArrowRight size={17} aria-hidden="true" /></Link>
              <a href="#workflow" className={styles.secondaryAction}>Follow the workflow <span aria-hidden="true">↓</span></a>
            </div>
            <p className={styles.heroNote}>Built around the water, the infrastructure, and the people who manage it.</p>
          </div>
          <figure className={styles.productFigure}>
            <div className={styles.figureHeading}><span><Waves size={15} aria-hidden="true" /> AquaVision</span><span>WATER OPERATIONS</span></div>
            <div className={styles.productImage}>
              <Image src="/landing/aquavision-infrastructure.png" alt="Actual AquaVision infrastructure screen showing reservoir and barrage observations, source freshness, inflow, outflow, and asset alert indicators." width={1126} height={635} priority sizes="(max-width: 900px) 92vw, 52vw" />
            </div>
            <div className={styles.figureAnnotation}><span className={styles.annotationNumber}>01</span><div><strong>Infrastructure, with the context attached.</strong><p>Readings, freshness and alert indicators beside each asset.</p></div></div>
            <figcaption><span>Captured from the local demo · saved preview, not live readings.</span><a href="/landing/aquavision-infrastructure.png" target="_blank" rel="noreferrer">Full-size preview <ArrowUpRight size={11} aria-hidden="true" /></a></figcaption>
          </figure>
        </section>

        <div className={styles.basinStrip}>
          <span className={styles.stripLabel}>ALONG THE INDUS</span>
          <ol aria-label="Selected Indus monitoring locations">{['Tarbela', 'Chashma', 'Guddu', 'Sukkur', 'Kotri'].map((station) => <li key={station}><span aria-hidden="true" />{station}</li>)}</ol>
          <span className={styles.stripEnd}>Reservoirs. Barrages. Communities.</span>
        </div>

        <section className={styles.platform} id="platform" aria-labelledby="platform-heading">
          <div className={styles.platformIntro}>
            <p className={styles.eyebrow}>THE PLATFORM</p>
            <h2 id="platform-heading">Different responsibilities.<br />Shared information.</h2>
            <p>Water operators, analysts and administrators work from connected records, with access shaped by their role and geographic scope.</p>
          </div>
          <div className={styles.moduleList}>
            <article><span className={styles.moduleIndex}>01 / WATER</span><Waves size={25} aria-hidden="true" /><h3>AquaVision</h3><p>Review infrastructure observations, source bulletins and alerts across reservoirs, barrages and river stations.</p><span className={styles.moduleFoot}>IRSA readings · FFD bulletins · asset registry</span></article>
            <article><span className={styles.moduleIndex}>02 / OPERATIONS</span><Radio size={25} aria-hidden="true" /><h3>Flood & field intelligence</h3><p>Inspect flood advisories, experimental predictions and downstream impact alongside simulated PLC and RTU signals.</p><span className={styles.moduleFoot}>Forecasts · impact analysis · Soft OT simulation</span></article>
            <article><span className={styles.moduleIndex}>03 / LAND</span><Sprout size={25} aria-hidden="true" /><h3>Crops & geography</h3><p>Explore regional crop analysis and geospatial views to connect water conditions with agricultural planning.</p><span className={styles.moduleFoot}>Crop Yield · GeoVision · regional indicators</span></article>
          </div>
          <div className={styles.dataNote}><ShieldCheck size={16} aria-hidden="true" /><p>Official observations, model predictions and simulated telemetry carry distinct labels throughout the platform.</p></div>
        </section>

        <section className={styles.workflow} id="workflow" aria-labelledby="workflow-heading">
          <div className={styles.workflowIntro}><div><p className={styles.eyebrow}>FROM SOURCE TO ACTION</p><h2 id="workflow-heading">When the water rises,<br /><em>follow the evidence.</em></h2></div><p>Consider a rising discharge at Guddu barrage. The platform helps an operator follow the source, review the condition and record a response.<small>Example operator workflow</small></p></div>
          <ol className={styles.workflowSteps}>{WORKFLOW.map(({title, body, tag, icon: Icon}, index) => <li key={title}><div className={styles.stepTop}><span>{String(index + 1).padStart(2, '0')}</span><Icon size={20} aria-hidden="true" /></div><h3>{title}</h3><p>{body}</p><span className={styles.stepTag}>{tag}</span></li>)}</ol>
        </section>

        <section className={styles.access} aria-labelledby="access-heading">
          <div><p className={styles.eyebrow}>THE OPERATIONS WORKSPACE</p><h2 id="access-heading">Take a closer look.</h2><p>Sign in with your assigned account to open the tools available to your role.</p></div>
          <Link href={consoleHref} className={styles.primaryAction}>{signedIn ? 'Return to workspace' : 'Sign in to IBCP-SCADA'}<ArrowRight size={17} aria-hidden="true" /></Link>
        </section>
      </main>
      <footer className={styles.footer}><div className={styles.footerBrand}><BrandMark width={23} height={23} /><span>IBCP-SCADA</span></div><p>Indus Basin Cyber-Physical SCADA System</p><span>Water · Land · Intelligence</span></footer>
    </div>
  )
}
