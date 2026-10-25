import { useState, useRef, useEffect } from 'react';

interface LazyImageProps {
    src: string;
    alt: string;
    className?: string;
    imgClassName?: string;
    width?: number;
    height?: number;
}

const LazyImage = ({ src, alt, className = '', imgClassName = '', width, height }: LazyImageProps) => {
    const [isLoaded, setIsLoaded] = useState(false);
    const [isInView, setIsInView] = useState(false);
    const imgRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setIsInView(true);
                    observer.disconnect();
                }
            },
            { rootMargin: '200px' }
        );

        if (imgRef.current) {
            observer.observe(imgRef.current);
        }

        return () => observer.disconnect();
    }, []);

    // Generate WebP src from PNG src
    const webpSrc = src.replace(/\.png$/, '.webp');
    const isWebPAvailable = src.endsWith('.png');

    return (
        <div
            ref={imgRef}
            className={`${className} ${!isLoaded ? 'animate-pulse bg-white/5' : ''}`}
            style={width && height ? { aspectRatio: `${width}/${height}` } : undefined}
        >
            {isInView && (
                <picture>
                    {isWebPAvailable && <source srcSet={webpSrc} type="image/webp" />}
                    <img
                        src={src}
                        alt={alt}
                        className={`w-full h-full object-cover transition-opacity duration-500 ${isLoaded ? 'opacity-100' : 'opacity-0'} ${imgClassName}`}
                        onLoad={() => setIsLoaded(true)}
                        loading="lazy"
                        decoding="async"
                        width={width}
                        height={height}
                    />
                </picture>
            )}
        </div>
    );
};

export default LazyImage;
