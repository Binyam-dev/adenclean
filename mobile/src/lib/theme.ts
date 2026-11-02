// AdenClean design tokens. The palette comes from the website (forest, warm paper, lime).
// Light mode is paper and forest; dark mode flips the action color to lime so it stays
// the most visible thing on screen. Clay is reserved for errors.

export type Palette = {
  bg: string;
  surface: string;
  surfaceDeep: string;
  ink: string;
  inkSoft: string;
  line: string;
  primary: string; // main button and selected states
  onPrimary: string;
  accent: string; // lime: lit windows, highlights
  onAccent: string;
  hero: string; // the house card
  onHero: string;
  heroSoft: string;
  error: string;
  errorBg: string;
  success: string;
  successBg: string;
  focus: string;
};

export const palettes: { light: Palette; dark: Palette } = {
  light: {
    bg: '#F3F1E8',
    surface: '#FBFAF4',
    surfaceDeep: '#E9E7DB',
    ink: '#1C3B32',
    inkSoft: '#52665A',
    line: 'rgba(28, 59, 50, 0.18)',
    primary: '#244B3F',
    onPrimary: '#F3F1E8',
    accent: '#D6E28E',
    onAccent: '#18372F',
    hero: '#244B3F',
    onHero: '#F3F1E8',
    heroSoft: '#A9B8A0',
    error: '#A5472B',
    errorBg: '#F5E4DB',
    success: '#2D5A3D',
    successBg: '#E3EBCB',
    focus: '#244B3F',
  },
  dark: {
    bg: '#0F1F1A',
    surface: '#16302A',
    surfaceDeep: '#1D3B33',
    ink: '#EEF2E4',
    inkSoft: '#A9B8A0',
    line: 'rgba(238, 242, 228, 0.18)',
    primary: '#D6E28E',
    onPrimary: '#18372F',
    accent: '#D6E28E',
    onAccent: '#18372F',
    hero: '#1D3B33',
    onHero: '#EEF2E4',
    heroSoft: '#A9B8A0',
    error: '#F0A88E',
    errorBg: '#3A2620',
    success: '#D6E28E',
    successBg: '#243A2A',
    focus: '#D6E28E',
  },
};

export const fonts = {
  display: 'BricolageGrotesque_700Bold',
  displayHeavy: 'BricolageGrotesque_800ExtraBold',
  body: 'Figtree_400Regular',
  bodyMedium: 'Figtree_500Medium',
  bodySemi: 'Figtree_600SemiBold',
} as const;

export type TextVariant = 'display' | 'title' | 'heading' | 'body' | 'bodyStrong' | 'small' | 'caption';

// One clear scale. Line height is about 1.4 for body and 1.15 for large headlines.
export const type: Record<TextVariant, { fontFamily: string; fontSize: number; lineHeight: number; letterSpacing?: number }> = {
  display: { fontFamily: fonts.displayHeavy, fontSize: 36, lineHeight: 40, letterSpacing: -0.9 },
  title: { fontFamily: fonts.display, fontSize: 27, lineHeight: 31, letterSpacing: -0.5 },
  heading: { fontFamily: fonts.display, fontSize: 20, lineHeight: 25, letterSpacing: -0.25 },
  body: { fontFamily: fonts.body, fontSize: 16, lineHeight: 24 },
  bodyStrong: { fontFamily: fonts.bodySemi, fontSize: 16, lineHeight: 24 },
  small: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  caption: { fontFamily: fonts.bodyMedium, fontSize: 13, lineHeight: 18 },
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, huge: 48 } as const;

// Radii step with importance: the hero is softest, controls are tighter.
export const radius = { hero: 30, card: 22, control: 16, chip: 14, window: 6, pill: 999 } as const;

export const MIN_TOUCH = 48;
export const MAX_WIDTH = 560;
