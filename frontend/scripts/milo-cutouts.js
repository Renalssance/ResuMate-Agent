// Cutout contours in the original 1312 × 1199 image coordinates.
// Exported PNGs retain original pixels. No resampling or mesh deformation.
const W=1312,H=1199;
const paths={
 leftEye:'M399 452 C397 408 433 367 476 352 C522 331 569 355 593 395 C621 441 606 483 576 510 C539 549 478 552 433 526 C405 509 394 480 399 452 Z',
 rightEye:'M737 531 C741 486 775 447 816 443 C865 439 908 472 925 514 C943 556 925 598 893 621 C859 650 815 641 780 617 C747 597 730 560 737 531 Z',
 nose:'M625 535 C634 523 659 527 675 538 C686 548 673 559 655 567 C641 574 626 553 625 535 Z',
 resume:'M648 711 C651 692 665 681 683 685 L893 709 Q919 713 914 739 L865 1042 Q861 1070 839 1066 L611 1038 Q586 1034 591 1010 Z',
 paw:'M821 890 C830 853 854 830 890 832 C932 831 965 861 973 899 C980 939 956 972 915 981 C873 992 838 967 825 940 C816 924 814 908 821 890 Z',
 leftIris:'M445 447 C445 408 475 379 508 378 C550 374 585 398 592 437 C601 477 570 515 533 523 C489 531 451 498 445 461 Z',
 rightIris:'M752 536 C753 500 779 472 809 469 C845 462 879 483 888 522 C899 561 878 596 845 608 C809 620 773 598 758 565 Z',
};
function surface(){const c=document.createElement('canvas');c.width=W;c.height=H;return c;}
function cut(image,path){const c=surface(),ctx=c.getContext('2d');ctx.save();ctx.clip(new Path2D(path));ctx.drawImage(image,0,0);ctx.restore();return c;}
function irisCut(image,path){
 const candidate=surface(),c=candidate.getContext('2d');c.fill(new Path2D(path));c.lineWidth=14;c.stroke(new Path2D(path));c.globalCompositeOperation='source-in';c.drawImage(image,0,0);
 const pixels=c.getImageData(0,0,W,H);
 for(let i=0;i<pixels.data.length;i+=4){const d=pixels.data,r=d[i],g=d[i+1],b=d[i+2];const blue=Math.max(0,Math.min(1,(g-r-3)/8));const dark=Math.max(0,Math.min(1,(135-Math.max(r,g,b))/20));d[i+3]*=Math.max(blue,dark);}
 c.putImageData(pixels,0,0);return candidate;
}
function crop(canvas,rect){const [x,y,w,h]=rect,c=document.createElement('canvas');c.width=w;c.height=h;c.getContext('2d').drawImage(canvas,x,y,w,h,0,0,w,h);return {canvas:c,x,y,w,h};}
export async function buildLayers(){
 const image=new Image();image.src='/images/milo-welcome.png';await image.decode();
 const layers={};
 for(const [side,rect] of [['left',[386,335,232,220]],['right',[726,432,216,220]]]){
  const eye=paths[side+'Eye'],iris=paths[side+'Iris'];
  const irisLayer=irisCut(image,iris);
  const white=cut(image,eye),ctx=white.getContext('2d');
  // Remove the original iris entirely. Restore the white sphere underneath it.
  ctx.globalCompositeOperation='destination-out';ctx.filter='blur(2px)';ctx.drawImage(irisLayer,0,0);ctx.filter='none';ctx.drawImage(irisLayer,0,0);
  ctx.globalCompositeOperation='destination-over';ctx.save();ctx.clip(new Path2D(eye));
  const fill=ctx.createLinearGradient(rect[0],rect[1],rect[0]+rect[2],rect[1]+rect[3]);fill.addColorStop(0,'#fffdf8');fill.addColorStop(.5,'#f9f5ee');fill.addColorStop(1,'#ede5db');ctx.fillStyle=fill;ctx.fillRect(...rect);ctx.restore();
  layers[side+'-eye']=crop(white,rect);layers[side+'-iris']=crop(irisLayer,rect);
 }
 layers.nose=crop(cut(image,paths.nose),[615,518,78,64]);
 const card=cut(image,paths.resume),cc=card.getContext('2d');cc.globalCompositeOperation='destination-out';cc.fill(new Path2D(paths.paw));
 layers.resume=crop(card,[580,675,345,400]);
 layers.paw=crop(cut(image,paths.paw),[807,824,176,171]);
 return layers;
}
