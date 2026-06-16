interface DamanLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

export default function DamanLogo({ className = '', size = 'md' }: DamanLogoProps) {
  const sizeMap = {
    sm: 'h-8',
    md: 'h-10',
    lg: 'h-12',
    xl: 'h-16',
  };

  return (
    <img
      src="/logo (2).svg"
      alt="DAMAN Securities"
      className={`${sizeMap[size]} w-auto ${className}`}
    />
  );
}
