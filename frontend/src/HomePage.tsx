import "./home.css";

type HomePageProps = { navigate: (path: string) => void };

function Brand() {
  return (
    <a className="brand" href="#/" aria-label="Hisaab home">
      <span className="brand-mark">h</span>
      <span>hisaab<span className="brand-period">.</span></span>
    </a>
  );
}

function HomePage({ navigate }: HomePageProps) {
  return (
    <div className="home-page">
      <div className="announcement"><span className="live-dot" /> A kinder way to keep your khata in order <span className="announcement-end">Made for neighborhood shops&nbsp; ↗</span></div>
      <header className="topbar home-topbar">
        <Brand />
        <nav className="nav-links" aria-label="Main navigation">
          <a className="nav-active" href="#home">Home</a>
          <a href="#how-it-works">How it works</a>
          <a href="#for-everyone">For customers</a>
        </nav>
        <div className="home-actions">
          <button className="home-login" type="button" onClick={() => navigate("login")}>Log in</button>
          <button className="button home-signup" type="button" onClick={() => navigate("login")}>Shopkeeper login <span>↗</span></button>
        </div>
      </header>

      <main className="home-main" id="home">
        <section className="home-hero">
          <div className="home-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> YOUR KHATA, WITH A VOICE</div>
            <h1>Udhaar follow-up,<br /><span>with a little more</span><br />understanding.</h1>
            <p className="home-subtitle">A clear khata for your shop. A polite voice to help you follow up, while keeping your customer relationships close.</p>
            <div className="home-hero-actions">
              <button className="button home-primary" onClick={() => navigate("login")} type="button">Shopkeeper login <span>↗</span></button>
              <a className="button home-secondary" href="#how-it-works">How it works <span>↓</span></a>
            </div>
            <p className="home-note"><span>✳</span> Calls happen only when you choose to make one.</p>
          </div>
          <div className="home-visual" aria-label="A simple illustration of a shopkeeper's khata">
            <div className="home-orbit home-orbit-one" /><div className="home-orbit home-orbit-two" /><div className="home-orbit home-orbit-three" />
            <div className="khata-card">
              <div className="khata-card-head"><span className="mini-brand-mark">h</span><span><b>Today’s khata</b><small>A calmer way to follow up</small></span><span className="khata-dots">•••</span></div>
              <div className="khata-divider" />
              <div className="khata-total-label">TOTAL UDHAAR PENDING</div><div className="khata-total">₹ 12,450</div><div className="khata-change"><span>↗</span> Across 8 customer accounts</div>
              <div className="khata-people"><span className="mini-avatar avatar-peach">R</span><span className="mini-avatar avatar-sage">A</span><span className="mini-avatar avatar-blue">M</span><span className="mini-avatar avatar-lilac">S</span><span className="people-label">Your neighborhood, in one place</span></div>
              <div className="khata-reminder"><span className="reminder-icon">⌁</span><span><b>A gentle reminder</b><small>In Hindi or Hinglish, when you say so.</small></span><span className="reminder-arrow">↗</span></div>
            </div>
            <div className="float-note float-note-top"><span className="float-icon">✓</span><span>Payment promise<br /><b>saved for later</b></span></div>
            <div className="float-note float-note-bottom"><span className="float-icon warm">♡</span><span>Kind words.<br /><b>Better follow-up.</b></span></div>
            <span className="visual-star visual-star-one">✳</span><span className="visual-star visual-star-two">✦</span>
          </div>
          <div className="home-stamp"><span>✳</span> BUILT FOR<br />YOUR SHOP</div>
        </section>

        <section className="home-trust-strip" aria-label="Hisaab values">
          <span className="trust-heading">MADE FOR THE WAY YOUR SHOP WORKS</span>
          <span><i>✓</i> Your khata stays clear</span><span><i>♡</i> Keep it neighborly</span><span><i>⌁</i> Speak their language</span>
        </section>

        <section className="home-how" id="how-it-works">
          <div className="home-section-heading"><span className="section-kicker">SIMPLE BY DESIGN</span><h2>Less chasing. More clarity.</h2><p>Let Hisaab take care of the follow-up, while you take care of your shop.</p></div>
          <div className="home-feature-grid">
            <article className="home-feature"><span className="feature-icon icon-khata">₹</span><span className="feature-number">01 / YOUR LEDGER</span><h3>See the full picture</h3><p>Every customer balance and payment promise in one simple khata.</p><a href="#/dashboard">Open shop dashboard <span>↗</span></a></article>
            <article className="home-feature"><span className="feature-icon icon-voice">⌁</span><span className="feature-number">02 / A POLITE CALL</span><h3>Follow up with care</h3><p>Choose a customer and let a gentle Hindi or Hinglish voice reminder do the asking.</p><a href="#/dashboard">Make a follow-up <span>↗</span></a></article>
            <article className="home-feature"><span className="feature-icon icon-promise">✓</span><span className="feature-number">03 / WHAT COMES NEXT</span><h3>Keep every promise</h3><p>See call outcomes and payment dates together, so nothing slips through the cracks.</p><a href="#/dashboard">See call activity <span>↗</span></a></article>
          </div>
        </section>

        <section className="customer-band" id="for-everyone">
          <div className="customer-band-art"><span className="band-orbit band-orbit-a" /><span className="band-orbit band-orbit-b" /><span className="band-center">♡</span></div>
          <div className="customer-band-copy"><span className="section-kicker">ONE OWNER ACCOUNT FOR THIS DEMO</span><h2>Udhaar works best<br />when trust goes both ways.</h2><p>For now, only the shop owner can sign in and see the shop’s khata. Customer accounts can be added when you are ready.</p><button className="button band-button" onClick={() => navigate("login")} type="button">Shopkeeper login <span>↗</span></button></div>
        </section>

        <section className="home-bottom-cta"><span className="section-kicker">A LITTLE MORE PEACE OF MIND</span><h2>Ready to make your khata<br />feel lighter?</h2><p>Sign in with the shop owner’s verified mobile number.</p><button className="button home-primary" onClick={() => navigate("login")} type="button">Shopkeeper login <span>↗</span></button></section>
      </main>
      <footer className="home-footer"><Brand /><span>Made for the people who keep the neighborhood running.</span><div><button onClick={() => navigate("login")} type="button">Shopkeeper login</button></div></footer>
    </div>
  );
}

export default HomePage;
