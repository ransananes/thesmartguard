import React, { useRef, useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Maximize2, Minimize2, WifiOff, X, GripHorizontal } from 'lucide-react';

const PIP_SIZES = [
    { w: 240, h: 135 },
    { w: 400, h: 225 },
    { w: 560, h: 315 },
];

const VideoPlayer = ({ streamUrl, pipUrl, showPip, onClosePip }) => {
    const playerWrapperRef = useRef(null);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [hasError, setHasError] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);

    // PiP drag + size state
    const [pipPos, setPipPos] = useState(null); // null = default bottom-right corner
    const [pipSizeIdx, setPipSizeIdx] = useState(0);
    const isDragging = useRef(false);
    const dragOffset = useRef({ x: 0, y: 0 });

    useEffect(() => {
        setHasError(false);
        setIsPlaying(false);
    }, [streamUrl]);

    // Mouse drag handlers for PiP
    useEffect(() => {
        const onMove = (e) => {
            if (!isDragging.current || !playerWrapperRef.current) return;
            const { w, h } = PIP_SIZES[pipSizeIdx];
            const rect = playerWrapperRef.current.getBoundingClientRect();
            let x = e.clientX - rect.left - dragOffset.current.x;
            let y = e.clientY - rect.top - dragOffset.current.y;
            x = Math.max(0, Math.min(rect.width - w, x));
            y = Math.max(0, Math.min(rect.height - h, y));
            setPipPos({ x, y });
        };
        const onUp = () => { isDragging.current = false; };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        return () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
    }, [pipSizeIdx]);

    const handlePipMouseDown = (e) => {
        if (e.target.closest('[data-pip-close]')) return;
        e.preventDefault();
        const pipRect = e.currentTarget.getBoundingClientRect();
        dragOffset.current = {
            x: e.clientX - pipRect.left,
            y: e.clientY - pipRect.top,
        };
        isDragging.current = true;
    };

    const { w: pipW, h: pipH } = PIP_SIZES[pipSizeIdx];

    const pipStyle = {
        width: pipW,
        height: pipH,
        transition: 'width 0.2s ease, height 0.2s ease',
        ...(pipPos
            ? { top: pipPos.y, left: pipPos.x }
            : { bottom: 52, right: 12 }),
    };

    const handlePipDoubleClick = (e) => {
        if (e.target.closest('[data-pip-close]')) return;
        e.preventDefault();
        setPipSizeIdx(i => (i + 1) % PIP_SIZES.length);
    };

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
        console.log('Stream error detected for:', streamUrl);
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
                            onError={(e) => { console.error('Native Video Error:', e); handleError(); }}
                        />
                    ) : streamUrl && streamUrl.includes('video_feed') ? (
                        <img
                            src={streamUrl}
                            alt="Live Stream"
                            className="absolute top-0 left-0 w-full h-full object-contain"
                            onError={(e) => { console.error('MJPEG Stream Error:', e); handleError(); }}
                        />
                    ) : null}

                    {/* ── Picture-in-Picture robot camera ── */}
                    {showPip && pipUrl && (
                        <div
                            onMouseDown={handlePipMouseDown}
                            onDoubleClick={handlePipDoubleClick}
                            className="absolute z-20 rounded-xl overflow-hidden border-2 border-purple-500/70 shadow-2xl shadow-black/80 cursor-grab active:cursor-grabbing select-none"
                            style={pipStyle}
                        >
                            <img
                                src={pipUrl}
                                alt="Robot Camera"
                                className="w-full h-full object-cover"
                                draggable={false}
                            />
                            {/* Header bar */}
                            <div className="absolute top-0 left-0 right-0 flex items-center justify-between px-2 py-1 bg-black/70 backdrop-blur-sm pointer-events-none">
                                <div className="flex items-center gap-1.5">
                                    <GripHorizontal size={10} className="text-purple-400 opacity-70" />
                                    <span className="text-[9px] text-purple-300 font-bold tracking-widest uppercase">Robot Cam</span>
                                </div>
                                <button
                                    data-pip-close="true"
                                    onClick={(e) => { e.stopPropagation(); onClosePip?.(); }}
                                    className="pointer-events-auto text-white/60 hover:text-white transition-colors leading-none"
                                >
                                    <X size={12} />
                                </button>
                            </div>
                            {/* Live badge */}
                            <div className="absolute bottom-1.5 left-2 flex items-center gap-1">
                                <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                                <span className="text-[8px] text-white/70 font-bold tracking-widest uppercase">Live</span>
                            </div>
                        </div>
                    )}

                    {/* Fullscreen + controls overlay */}
                    <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex justify-end pointer-events-none">
                        <button
                            onClick={toggleFullscreen}
                            className="p-2 rounded-full hover:bg-white/10 transition-colors text-white pointer-events-auto"
                        >
                            {isFullscreen ? <Minimize2 size={20} /> : <Maximize2 size={20} />}
                        </button>
                    </div>

                    {/* Live badge (main stream) */}
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
    pipUrl: PropTypes.string,
    showPip: PropTypes.bool,
    onClosePip: PropTypes.func,
};

export default VideoPlayer;
