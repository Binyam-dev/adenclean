import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';

import { usePalette } from './use-palette';

// The AdenClean house. Each window lights up lime when its part of the request is done,
// so progress through the form is something you can see on the building itself.
const VIEW_W = 200;
const VIEW_H = 190;
// x, y, width, height in the 200 x 190 drawing
const WINDOWS: [number, number, number, number][] = [
  [58, 92, 30, 28],
  [112, 92, 30, 28],
  [44, 134, 32, 28],
  [124, 134, 32, 28],
];

type Props = {
  /** One flag per window, in order. */
  lit: boolean[];
  size?: number;
  /** Light the windows one after another when first shown (the home screen). */
  introduce?: boolean;
  tone?: 'hero' | 'plain';
};

export function House({ lit, size = 200, introduce = false, tone = 'plain' }: Props) {
  const p = usePalette();
  const outline = tone === 'hero' ? p.onHero : p.ink;
  const unlit = tone === 'hero' ? 'rgba(243,241,232,0.10)' : p.surfaceDeep;
  const [values] = useState(() => WINDOWS.map(() => new Animated.Value(introduce ? 0 : 1)));
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    void AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
  }, []);

  useEffect(() => {
    const animations = values.map((value, index) => {
      const target = lit[index] ? 1 : 0;
      if (reduceMotion) {
        value.setValue(target);
        return null;
      }
      return Animated.timing(value, {
        toValue: target,
        duration: 380,
        delay: introduce ? 450 + index * 170 : 0,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: false,
      });
    });
    animations.forEach((animation) => animation?.start());
    return () => animations.forEach((animation) => animation?.stop());
  }, [lit, introduce, values, reduceMotion]);

  const litCount = lit.filter(Boolean).length;
  const height = (size * VIEW_H) / VIEW_W;

  return (
    <View
      style={{ width: size, height }}
      accessible
      accessibilityRole="image"
      accessibilityLabel={`House with ${litCount} of ${lit.length} windows lit`}>
      <Svg width={size} height={height} viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} fill="none">
        <Path d="M20 92 100 24l80 68" stroke={outline} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
        <Path
          d="M34 82v84a8 8 0 0 0 8 8h116a8 8 0 0 0 8-8V82"
          stroke={outline}
          strokeWidth={5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <Rect x={88} y={126} width={24} height={48} rx={5} stroke={outline} strokeWidth={5} />
        <Path d="M152 36l9-8M166 50l10-3M100 10V2" stroke={p.accent} strokeWidth={5} strokeLinecap="round" />
      </Svg>
      {WINDOWS.map(([x, y, w, h], index) => (
        <Animated.View
          key={index}
          pointerEvents="none"
          style={[
            styles.window,
            {
              left: (x / VIEW_W) * size,
              top: (y / VIEW_H) * height,
              width: (w / VIEW_W) * size,
              height: (h / VIEW_H) * height,
              borderRadius: (6 / VIEW_W) * size,
              backgroundColor: values[index].interpolate({
                inputRange: [0, 1],
                outputRange: [unlit, p.accent],
              }),
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  window: { position: 'absolute' },
});
