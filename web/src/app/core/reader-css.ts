import {
  READER_FONTS,
  READER_THEMES,
  type ReaderPreferences,
  type ReaderStyle,
} from './reader-preferences';

/**
 * The rules of the style of a printed book.
 *
 * They are appended to the stylesheet of the reader when the style is
 * `book`: the text is justified and hyphenated, the paragraphs are marked
 * with an indent instead of a blank line, and the headings are set in small
 * capitals.
 */
const BOOK_STYLE = `
    body {
      text-align: justify !important;
      hyphens: auto !important;
      -webkit-hyphens: auto !important;
      text-justify: inter-word;
    }
    p {
      margin-block: 0 !important;
      text-indent: 1.4em;
    }
    p + p {
      margin-block-start: 0 !important;
    }
    h1 + p, h2 + p, h3 + p, h4 + p, h5 + p, h6 + p,
    blockquote > p:first-of-type, li > p:first-of-type, td > p:first-of-type {
      text-indent: 0;
    }
    h1, h2, h3, h4, h5, h6 {
      text-align: center;
      font-variant: small-caps;
      letter-spacing: 0.05em;
      font-weight: 600;
      margin-block: 1.5em 0.8em !important;
      text-indent: 0;
    }
    h1:first-child, h2:first-child, h3:first-child {
      margin-block-start: 0 !important;
    }
    blockquote {
      font-style: italic;
      margin-inline: 1.5em !important;
    }
    hr {
      width: 35%;
      margin-inline: auto;
    }
`;

/**
 * Build the stylesheet that the reader injects in the pages of the book.
 *
 * The stylesheet is applied by foliate-js to every section of the EPUB, so
 * the settings of the reader win over the ones of the book.
 */
export function buildReaderCss(preferences: ReaderPreferences): string {
  const font =
    READER_FONTS.find((candidate) => candidate.id === preferences.font)?.stack ??
    READER_FONTS[0].stack;
  const theme =
    READER_THEMES.find((candidate) => candidate.id === preferences.theme) ?? READER_THEMES[0];
  const margin = Math.max(0, Math.round(preferences.margin));
  const size = Math.max(10, Math.round(preferences.size));
  const leading = Math.max(1, preferences.leading);
  const style: ReaderStyle = preferences.style;

  return `
    html {
      color-scheme: ${theme.scheme};
      background-color: ${theme.background} !important;
    }
    body {
      font-family: ${font} !important;
      font-size: ${size}px !important;
      line-height: ${leading} !important;
      color: ${theme.foreground} !important;
      background-color: ${theme.background} !important;
      padding: ${margin}px !important;
      text-align: start;
      widows: 2;
      orphans: 2;
    }
    h1, h2, h3, h4, h5, h6 {
      font-family: ${font} !important;
      line-height: ${leading} !important;
    }
    p, li, blockquote, dd, dt {
      line-height: ${leading} !important;
    }
    a {
      color: ${theme.link} !important;
    }
    img, svg, video {
      max-width: 100%;
      height: auto;
    }
    pre {
      white-space: pre-wrap !important;
    }
    ${style === 'book' ? BOOK_STYLE : ''}
  `;
}
