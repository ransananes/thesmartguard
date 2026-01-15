import React, { useRef, useState, useEffect } from 'react';
import ReactPlayer from 'react-player';
import PropTypes from 'prop-types';
import { Maximize2, Minimize2, WifiOff } from 'lucide-react';

const VideoPlayer = ({ streamUrl }) => {
    const playerWrapperRef = useRef(null);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [hasError, setHasError] = useState(false);

    const [isPlaying, setIsPlaying] = useState(false);

    // Reset error state and playing state when stream URL changes
    useEffect(() => {
        setHasError(false);
        setIsPlaying(false);
    }, [streamUrl]);

    const toggleFullscreen = () => {
        if (!document.fullscreenElement) {
            playerWrapperRef.current.requestFullscreen();
            setIsFullscreen(true);
        } else {
            document.exitFullscreen();
            setIsFullscreen(false);
        }
    };

    const handleError = () => {
        console.log("Stream error detected for:", streamUrl);
        setHasError(true);
    };

    return (
        <div 
            ref={playerWrapperRef}
            className="relative w-full aspect-video bg-black rounded-xl overflow-hidden shadow-2xl border border-white/10 group bg-neutral-900"
        >
            {!hasError ? (
                <>
                    {streamUrl && (streamUrl.endsWith('.mp4') || streamUrl.includes('google')) ? (
                        <video
                            key={streamUrl}
                            src={streamUrl}
                            autoPlay
                            muted
                            playsInline
                            controls
                            loop
                            className="absolute top-0 left-0 w-full h-full object-contain"
                            onError={(e) => {
                                console.error('Native Video Error:', e);
                                handleError();
                            }}
                        />
                    ) : streamUrl && streamUrl.includes('video_feed') ? (
                        <img 
                            src={streamUrl} 
                            alt="Live Stream" 
                            className="absolute top-0 left-0 w-full h-full object-contain"
                            onError={(e) => {
                                console.error('MJPEG Stream Error:', e);
                                handleError();
                            }}
                        />
                    ) : (
                        <ReactPlayer
                            url={streamUrl}
                            playing={isPlaying}
                            muted={true}
                            playsinline={true}
                            controls={true}
                            width="100%"
                            height="100%"
                            className="absolute top-0 left-0"
                            onReady={() => {
                                console.log('ReactPlayer: Ready');
                                setIsPlaying(true);
                            }}
                            onStart={() => console.log('ReactPlayer: Started')}
                            onError={(e) => {
                                console.error('ReactPlayer: Error', e);
                                handleError();
                            }}
                        />
                    )}
                    
                    {/* Controls */}
                    <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex justify-end pointer-events-none">
                        <button 
                            onClick={toggleFullscreen}
                            className="p-2 rounded-full hover:bg-white/10 transition-colors text-white pointer-events-auto"
                        >
                            {isFullscreen ? <Minimize2 size={20} /> : <Maximize2 size={20} />}
                        </button>
                    </div>
                    
                    {/* Live Indicator */}
                    <div className="absolute top-4 left-4 px-3 py-1 rounded-full bg-red-600/80 backdrop-blur-sm flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                        <span className="text-white text-xs font-bold tracking-widest uppercase">Live</span>
                    </div>
                </>
            ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-neutral-400 gap-4 bg-neutral-900/50 backdrop-blur-sm">
                    <div className="relative">
                        <div className="absolute inset-0 bg-red-500/20 blur-xl rounded-full animate-pulse" />
                        <WifiOff size={48} className="text-red-500 relative z-10" />
                    </div>
                    <div className="text-center">
                        <h3 className="text-white font-bold text-lg mb-1">Signal Lost</h3>
                        <p className="text-sm text-neutral-500">Camera feed unavailable</p>
                    </div>
                    <button 
                        onClick={() => setHasError(false)}
                        className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-white text-sm rounded-lg transition-colors border border-white/5"
                    >
                        Retry Connection
                    </button>
                </div>
            )}
        </div>
    );
};

VideoPlayer.propTypes = {
    streamUrl: PropTypes.string.isRequired,
};

export default VideoPlayer;
