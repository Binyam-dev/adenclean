// Where the app talks to. Set EXPO_PUBLIC_API_URL (see eas.json) to the deployed server.
const raw = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:5000';

export const API_URL = raw.replace(/\/+$/, '');

// Contact details shown in the app. Keep these in step with the website.
export const SUPPORT_EMAIL = 'applications@adeneats.com';
export const SUPPORT_PHONE_DISPLAY = '(240) 342-6088';
export const SUPPORT_PHONE_LINK = 'tel:+12403426088';

export const PRIVACY_URL = `${API_URL}/policies.html#privacy`;
export const TERMS_URL = `${API_URL}/policies.html#service`;
export const SERVICE_AREA = 'Silver Spring, Maryland';
