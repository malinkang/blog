const urlPattern = /https?:\/\/[^\s<>()"'，。！？、；：（）【】《》「」『』]+/g;
const skipTags = new Set(['A', 'CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA']);

function shouldSkip(node: Node): boolean {
    let parent = node.parentElement;
    while (parent) {
        if (skipTags.has(parent.tagName)) return true;
        parent = parent.parentElement;
    }
    return false;
}

function linkifyBareUrls(root: Element): void {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            if (!node.textContent || !urlPattern.test(node.textContent) || shouldSkip(node)) {
                urlPattern.lastIndex = 0;
                return NodeFilter.FILTER_REJECT;
            }
            urlPattern.lastIndex = 0;
            return NodeFilter.FILTER_ACCEPT;
        },
    });

    const textNodes: Text[] = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode as Text);

    textNodes.forEach((node) => {
        const text = node.textContent || '';
        const fragment = document.createDocumentFragment();
        let lastIndex = 0;

        text.replace(urlPattern, (match, offset) => {
            if (offset > lastIndex) fragment.append(text.slice(lastIndex, offset));

            const link = document.createElement('a');
            link.href = match;
            link.textContent = match;
            link.className = 'link';
            link.target = '_blank';
            link.rel = 'noopener';
            fragment.append(link);

            lastIndex = offset + match.length;
            return match;
        });

        if (lastIndex < text.length) fragment.append(text.slice(lastIndex));
        node.replaceWith(fragment);
    });
}

window.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.article-content').forEach(linkifyBareUrls);
});
