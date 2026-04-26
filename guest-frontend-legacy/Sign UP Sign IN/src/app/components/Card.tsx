import { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  glowColor?: 'blue' | 'rose' | 'none';
}

export function Card({ children, className = '', glowColor = 'none' }: CardProps) {
  const glowStyles = {
    blue: 'shadow-[0_0_40px_rgba(59,130,246,0.1)]',
    rose: 'shadow-[0_0_40px_rgba(244,63,94,0.1)]',
    none: ''
  };

  return (
    <div className={`bg-gradient-to-br from-gray-900 to-gray-950 border border-gray-800 rounded-2xl p-8 backdrop-blur-sm ${glowStyles[glowColor]} ${className}`}>
      {children}
    </div>
  );
}
