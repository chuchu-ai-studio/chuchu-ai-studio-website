// Register inquiry handling before unrelated page behavior.
const inquiryForm = document.querySelector('[data-inquiry-form]');
if (inquiryForm) {
  const submitButton = inquiryForm.querySelector('button[type="submit"]');
  const feedback = inquiryForm.querySelector('[data-inquiry-status]');
  const showFeedback = (state, message) => {
    feedback.dataset.state = state;
    feedback.textContent = message;
    feedback.hidden = false;
    feedback.focus();
  };
  inquiryForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submitButton.disabled || !inquiryForm.reportValidity()) return;
    const errorMessage = 'We couldn’t send your inquiry. Please try again or email hello@chuchuaistudio.com.';
    feedback.hidden = true;
    submitButton.disabled = true;
    submitButton.textContent = 'Sending…';
    inquiryForm.setAttribute('aria-busy', 'true');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(inquiryForm.action, {
        method: 'POST',
        body: new FormData(inquiryForm),
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error('Inquiry submission failed');
      inquiryForm.reset();
      showFeedback('success', 'Thanks — your project inquiry has been sent. CHUCHU AI STUDIO will review it and reply by email.');
    } catch {
      showFeedback('error', errorMessage);
    } finally {
      clearTimeout(timeout);
      submitButton.disabled = false;
      submitButton.textContent = 'Send Project Inquiry';
      inquiryForm.removeAttribute('aria-busy');
    }
  });
}

const header = document.querySelector('[data-header]');
const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('.site-nav');

const updateHeader = () => header.classList.toggle('scrolled', window.scrollY > 16);
updateHeader();
window.addEventListener('scroll', updateHeader, { passive: true });

menuButton.addEventListener('click', () => {
  const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!isOpen));
  menuButton.setAttribute('aria-label', isOpen ? 'Open navigation' : 'Close navigation');
  navigation.classList.toggle('open', !isOpen);
});

navigation.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    menuButton.setAttribute('aria-expanded', 'false');
    menuButton.setAttribute('aria-label', 'Open navigation');
    navigation.classList.remove('open');
  });
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && navigation.classList.contains('open')) {
    navigation.classList.remove('open');
    menuButton.setAttribute('aria-expanded', 'false');
    menuButton.focus();
  }
});

document.querySelector('[data-year]').textContent = new Date().getFullYear();

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (reducedMotion || !('IntersectionObserver' in window)) {
  document.querySelectorAll('.reveal').forEach((element) => element.classList.add('visible'));
} else {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach((element) => observer.observe(element));
}
