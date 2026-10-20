import '@mantine/core/styles.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { realApi } from './api/realApi';
import { registerRealApi } from './state/apiSelect';

registerRealApi(realApi);

const root = document.getElementById('root');
if (!root) throw new Error('Wurzelelement #root fehlt');
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
