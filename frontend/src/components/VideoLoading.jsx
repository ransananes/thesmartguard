import React from 'react';

const VideoLoading = () => {
    return (
        <div className="w-full aspect-video bg-neutral-900 rounded-xl border border-white/10 flex flex-col items-center justify-center">
            <div className="relative">
                <div className="absolute inset-0 bg-purple-500/20 blur-xl rounded-full animate-pulse" />
                <div className="w-12 h-12 border-4 border-purple-500/30 border-t-purple-500 rounded-full animate-spin" />
            </div>
            <p className="mt-4 text-neutral-400 text-sm">Loading camera...</p>
        </div>
    );
};

export default VideoLoading;
