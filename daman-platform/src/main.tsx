import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { ThemeProvider } from './contexts/ThemeContext';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>
);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        console.log('✅ Service Worker registered successfully:', registration.scope);

        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          console.log('🔄 New service worker found, installing...');

          newWorker?.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              console.log('✨ New version available! Refresh to update.');
            }
          });
        });
      })
      .catch((error) => {
        console.error('❌ Service Worker registration failed:', error);
      });
  });
}
