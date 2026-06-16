import { X, ExternalLink } from 'lucide-react';
import { useEffect } from 'react';

interface FeatureDetail {
  title: string;
  description: string;
  benefits: string[];
  specifications: { label: string; value: string }[];
  source: string;
}

interface FeatureModalProps {
  isOpen: boolean;
  onClose: () => void;
  feature: FeatureDetail | null;
}

export default function FeatureModal({ isOpen, onClose, feature }: FeatureModalProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      window.addEventListener('keydown', handleEscape);
    }

    return () => {
      window.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !feature) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900 bg-opacity-75 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden animate-slideUp"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-gradient-to-r from-daman-blue-600 to-daman-blue-700 px-6 py-5 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-white">{feature.title}</h2>
          <button
            onClick={onClose}
            className="text-white hover:bg-white hover:bg-opacity-20 rounded-lg p-2 transition-all"
            aria-label="Close modal"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        <div className="overflow-y-auto max-h-[calc(90vh-80px)] p-6">
          <p className="text-slate-700 text-lg leading-relaxed mb-6">
            {feature.description}
          </p>

          <div className="mb-6">
            <h3 className="text-xl font-bold text-slate-900 mb-4 flex items-center">
              <div className="w-1 h-6 bg-daman-blue-600 rounded-full mr-3"></div>
              Key Benefits
            </h3>
            <ul className="space-y-3">
              {feature.benefits.map((benefit, index) => (
                <li key={index} className="flex items-start">
                  <div className="bg-daman-blue-100 rounded-full p-1 mr-3 mt-0.5 flex-shrink-0">
                    <div className="w-2 h-2 bg-daman-blue-600 rounded-full"></div>
                  </div>
                  <span className="text-slate-700 leading-relaxed">{benefit}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="mb-6">
            <h3 className="text-xl font-bold text-slate-900 mb-4 flex items-center">
              <div className="w-1 h-6 bg-daman-blue-600 rounded-full mr-3"></div>
              Specifications
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {feature.specifications.map((spec, index) => (
                <div
                  key={index}
                  className="bg-slate-50 rounded-lg p-4 border border-slate-200"
                >
                  <div className="text-sm font-semibold text-slate-600 mb-1">
                    {spec.label}
                  </div>
                  <div className="text-lg font-bold text-slate-900">{spec.value}</div>
                </div>
              ))}
            </div>
          </div>


          <button
            onClick={onClose}
            className="w-full mt-6 bg-daman-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-daman-blue-700 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
