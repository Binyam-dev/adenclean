import { Text as RNText, type TextProps as RNTextProps } from 'react-native';

import { type TextVariant, type Palette, type as typeScale } from '@/lib/theme';

import { usePalette } from './use-palette';

export type Tone = 'ink' | 'soft' | 'primary' | 'onPrimary' | 'onHero' | 'heroSoft' | 'error' | 'success' | 'onAccent';

function toneColor(p: Palette, tone: Tone): string {
  switch (tone) {
    case 'soft':
      return p.inkSoft;
    case 'primary':
      return p.primary;
    case 'onPrimary':
      return p.onPrimary;
    case 'onHero':
      return p.onHero;
    case 'heroSoft':
      return p.heroSoft;
    case 'error':
      return p.error;
    case 'success':
      return p.success;
    case 'onAccent':
      return p.onAccent;
    default:
      return p.ink;
  }
}

export type TextProps = RNTextProps & { variant?: TextVariant; tone?: Tone };

export function Text({ variant = 'body', tone = 'ink', style, ...rest }: TextProps) {
  const p = usePalette();
  return <RNText {...rest} style={[typeScale[variant], { color: toneColor(p, tone) }, style]} />;
}
